param(
    [Parameter(Mandatory)][ValidateSet('Original_155250','H3_Base_145125','H3_Retained_145125')][string]$Release,
    [ValidateSet('Prepare','Build','Audit')][string]$Action = 'Build',
    [string]$BuildDirectory,
    [ValidateRange(0,2147483647)][int]$PlacementSeed,
    [ValidateSet('Shared42','NativeMinimal','Lean24')][string]$IlaProfile = 'Shared42',
    [switch]$StopAfterSynthesis
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$script:Utf8Bom = [System.Text.UTF8Encoding]::new($true)
$script:Utf8Plain = [System.Text.UTF8Encoding]::new($false)
$script:Mutex = $null
$script:MutexHeld = $false
$script:Manifest = $null

function Write-JsonFile([string]$Path, $Value) {
    [System.IO.File]::WriteAllText($Path, (($Value | ConvertTo-Json -Depth 32) + [Environment]::NewLine), $script:Utf8Bom)
}
function Write-Lines([string]$Path, [string[]]$Lines) {
    [System.IO.File]::WriteAllLines($Path, $Lines, $script:Utf8Plain)
}
function Get-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Get-Inventory([string]$Root) {
    $result = [ordered]@{}
    foreach ($file in Get-ChildItem -LiteralPath $Root -File -Recurse | Sort-Object FullName) {
        $relative = [System.IO.Path]::GetRelativePath($Root, $file.FullName).Replace([System.IO.Path]::DirectorySeparatorChar, '/')
        $result[$relative] = Get-Sha $file.FullName
    }
    return $result
}
function Get-TclPath([string]$Path) {
    $value = [System.IO.Path]::GetFullPath($Path).Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    if ($value -match '[{}"$;\r\n]') { throw 'Path contains Tcl control characters.' }
    return '{' + $value + '}'
}
function Save-Manifest {
    $script:Manifest.updated_utc = [datetime]::UtcNow.ToString('o')
    Write-JsonFile ([System.IO.Path]::Combine($script:Build, 'manifest.json')) $script:Manifest
}
function Invoke-Vendor([string]$Executable, [string[]]$Arguments, [string]$Directory, [string]$Label, [int]$TimeoutSeconds) {
    $Arguments = @($Arguments | ForEach-Object { $_.Replace([System.IO.Path]::DirectorySeparatorChar, '/') })
    $receiptPath = [System.IO.Path]::Combine($Directory, ($Label + '.invocation.json'))
    $stdout = [System.IO.Path]::Combine($Directory, ($Label + '.stdout.log'))
    $stderr = [System.IO.Path]::Combine($Directory, ($Label + '.stderr.log'))
    if (Test-Path -LiteralPath $receiptPath) {
        $archive=[System.IO.Path]::Combine($Directory,'invocations',($Label+'-'+[datetime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')))
        [void][System.IO.Directory]::CreateDirectory($archive)
        foreach ($old in @($receiptPath,$stdout,$stderr,[System.IO.Path]::Combine($Directory,'run.log'))) {
            if (Test-Path -LiteralPath $old -PathType Leaf) { Copy-Item -LiteralPath $old -Destination ([System.IO.Path]::Combine($archive,[System.IO.Path]::GetFileName($old))) }
        }
    }
    $receipt = [ordered]@{ executable=$Executable; executable_sha256=(Get-Sha $Executable); argv=$Arguments; working_directory=$Directory; started_utc=[datetime]::UtcNow.ToString('o'); pid=$null; exit_code=$null; stdout=$stdout; stderr=$stderr; status='starting' }
    Write-JsonFile $receiptPath $receipt
    $quoted = @($Arguments | ForEach-Object { if ($_ -match '[\r\n"]') { throw 'Invalid process argument.' }; if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
    $process = Start-Process -FilePath $Executable -ArgumentList $quoted -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $receipt.pid=$process.Id; $receipt.status='running'; Write-JsonFile $receiptPath $receipt
    Write-Host ('VENDOR ' + $Label + ' PID=' + $process.Id + ' DIRECTORY=' + $Directory)
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $process.WaitForExit(15000)) {
        if ($watch.Elapsed.TotalSeconds -gt $TimeoutSeconds) {
            $receipt.status='monitoring_timeout_process_retained'; Write-JsonFile $receiptPath $receipt
            throw ('Vendor monitoring timeout; inspect the recorded process and its children before resuming: ' + $process.Id)
        }
        Write-Host ('PROGRESS ' + $Label + ' elapsed_seconds=' + [int]$watch.Elapsed.TotalSeconds)
    }
    $process.WaitForExit()
    $receipt.exit_code=$process.ExitCode; $receipt.finished_utc=[datetime]::UtcNow.ToString('o'); $receipt.status='finished'; Write-JsonFile $receiptPath $receipt
    $output=[System.IO.File]::ReadAllText($stdout) + [Environment]::NewLine + [System.IO.File]::ReadAllText($stderr)
    if ($process.ExitCode -ne 0 -or $output -match '(?im)^\s*(E:|Error:)') { throw ('Vendor stage failed: ' + $Label + '; inspect ' + $stdout) }
    return $output
}
function Test-Inputs {
    $expected=Get-Content -LiteralPath ([System.IO.Path]::Combine($script:Build,'source-hashes.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    foreach ($relative in $expected.Keys) {
        foreach ($root in @($script:SourceInputs, [System.IO.Path]::Combine($script:Build,'frozen_inputs'))) {
            if ((Get-Sha ([System.IO.Path]::Combine($root,$relative))) -ne $expected[$relative]) { throw ('Frozen input hash mismatch: ' + $relative) }
        }
        if ($relative -ne 'pds_soc_top.v' -and (Get-Sha ([System.IO.Path]::Combine($script:Inputs,$relative))) -ne $expected[$relative]) { throw ('Functional input changed: ' + $relative) }
    }
    $original=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($script:SourceInputs,'pds_soc_top.v'))
    $modified=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($script:Inputs,'pds_soc_top.v'))
    $pattern='\.INIT_FILE\("[^"]+"\)'
    if ([regex]::Matches($original,$pattern).Count -ne 1 -or [regex]::Matches($modified,$pattern).Count -ne 1 -or [regex]::Replace($original,$pattern,'.INIT_FILE("FROZEN_FIRMWARE")') -cne [regex]::Replace($modified,$pattern,'.INIT_FILE("FROZEN_FIRMWARE")')) { throw 'Top wrapper differs beyond firmware path relocation.' }
    $firmware=Get-Sha ([System.IO.Path]::Combine($script:Inputs,'firmware.hex'))
    if ($firmware -ne $script:Manifest.firmware_sha256) { throw 'Frozen firmware hash mismatch.' }
    Write-Output ('INPUT AUDIT PASS: ' + $expected.Count + ' original hashes preserved; RTL/PLL/constraints/firmware unchanged; top INIT_FILE relocation only.')
}
function Resolve-Net([string]$Meaning,[string[]]$Candidates,[string[]]$Available) {
    $found=@($Candidates | Where-Object { $Available -ccontains $_ } | Select-Object -Unique)
    if ($found.Count -lt 1) { throw ('Native probe missing: ' + $Meaning + '; candidates=' + ($Candidates -join ', ')) }
    return $found[0]
}
function New-Fic([string]$Adf,[string[]]$Data,[string[]]$Trigger,[string]$Fic,[bool]$Shared) {
    $lines=[System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]]@('#Fabric Core Inserter Project File','Project.type=inserter',('Project.device.designInputFile=' + $Adf.Replace([System.IO.Path]::DirectorySeparatorChar,'/')),'Project.device.ScanChain=1','Project.device.UserJtag=0','Project.Architecture=1 1 1 ','Project.unit.dimension=1','Project.unit<0>.clockChannel=cpu_clk','Project.unit<0>.clockEdge=Rising'))
    if($Shared -and ($Data.Count -ne $Trigger.Count -or (Compare-Object $Data $Trigger -SyncWindow 0))) {throw 'Shared capture and trigger mapping must be identical.'}
    if(-not $Shared){for($i=0;$i -lt $Data.Count;$i++){$lines.Add('Project.unit<0>.dataChannel<'+$i+'>='+$Data[$i])};$lines.Add('Project.unit<0>.dataPortWidth='+$Data.Count)}
    $lines.AddRange([string[]]@('Project.unit<0>.ramType=1','Project.unit<0>.dataDepth=1024',('Project.unit<0>.dataEqualsTrigger='+$Shared.ToString().ToLowerInvariant()),'Project.unit<0>.enablePowerOnInitData=false','Project.unit<0>.enableStorageQualification=false','Project.unit<0>.triggerSequencerLevels=1','Project.unit<0>.enableMultiWindow=false','Project.unit<0>.triggerPortCount=1'))
    for($i=0;$i -lt $Trigger.Count;$i++) { $lines.Add('Project.unit<0>.triggerChannel<0><' + $i + '>=' + $Trigger[$i]) }
    $lines.AddRange([string[]]@('Project.unit<0>.triggerMatchCount<0>=1','Project.unit<0>.triggerMatchCountWidth<0>=0',('Project.unit<0>.triggerMatchType<0>='+[int]$Shared),'Project.unit<0>.triggerPortIsData<0>=true',('Project.unit<0>.triggerPortWidth<0>=' + $Trigger.Count)))
    Write-Lines $Fic $lines.ToArray()
}
function Get-CornerAudit([string]$Timing) {
    $sections=[regex]::Matches($Timing,'(?ms)^(Setup|Hold|Recovery|Removal|Minimum Pulse Width) Summary\((Slow Corner|Fast Corner)\):\s*(.*?)^={10,}\s*$')
    if($sections.Count -ne 10){throw 'Expected all ten setup/hold/recovery/removal/pulse-width corner summaries.'}
    $tables=[System.Collections.Generic.List[object]]::new()
    $allPassed=$true
    foreach($section in $sections) {
        $rows=[regex]::Matches($section.Groups[3].Value,'(?m)^(.*?)\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$')
        if($rows.Count -lt 1){throw ('Empty timing corner summary: '+$section.Groups[1].Value+' '+$section.Groups[2].Value)}
        $entries=[System.Collections.Generic.List[object]]::new()
        foreach($row in $rows) {
            $slack=[double]::Parse($row.Groups[2].Value,[Globalization.CultureInfo]::InvariantCulture)
            $tns=[double]::Parse($row.Groups[3].Value,[Globalization.CultureInfo]::InvariantCulture)
            $failing=[int]$row.Groups[4].Value
            $passed=($slack -ge 0 -and [math]::Abs($tns) -lt 0.0001 -and $failing -eq 0)
            $allPassed=$allPassed -and $passed
            $entries.Add([ordered]@{printed_clock_columns=$row.Groups[1].Value.Trim();slack_ns=$slack;total_negative_slack_ns=$tns;failing_endpoints=$failing;total_endpoints=[int]$row.Groups[5].Value;passed=$passed})
        }
        $tables.Add([ordered]@{check=$section.Groups[1].Value;corner=$section.Groups[2].Value;rows=$entries.ToArray()})
    }
    foreach($debugClock in @('DebugCore_JCLK','DebugCore_CAPTURE')) {if($Timing -notmatch ('(?m)^\s*'+$debugClock+'\s+[0-9.]+\s+\{[^}]+\}\s+Declared')){throw ('Debugger clock table missing: '+$debugClock)}}
    return [ordered]@{all_corners_passed=$allPassed;summary_tables_checked=$sections.Count;includes_cpu_and_debugger_clocks=$true;tables=$tables.ToArray()}
}
function Get-PhysicalReport([string]$Directory,[long]$ClockHz) {
    $timingPath=[System.IO.Path]::Combine($Directory,'report_timing','pds_soc_top.rtr')
    $timing=[System.IO.File]::ReadAllText($timingPath)
    $log=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($Directory,'run.log'))
    $clock='clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred'
    $clocks=[regex]::Matches($timing,'(?m)^\s*' + [regex]::Escape($clock) + '\s+([0-9.]+)\s+\{[^}]+\}\s+Generated \(clk\)\s+(\d+)')
    if($clocks.Count -ne 1) {throw 'CPU generated clock table missing or ambiguous.'}
    $period=[double]::Parse($clocks[0].Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)
    if([math]::Abs($period-1e9/$ClockHz) -gt 0.005 -or [int]$clocks[0].Groups[2].Value -lt 1) {throw 'CPU frequency or load count mismatch.'}
    $performance=[regex]::Matches($timing,[regex]::Escape($clock)+'\s+([0-9.]+) MHz\s+([0-9.]+) MHz\s+([0-9.]+)\s+([0-9.]+)\s+(-?[0-9.]+)')
    if($performance.Count -ne 1) {throw 'CPU performance summary missing or ambiguous.'}
    $cpuSetupPaths=@($timing -split '(?m)(?=^Startpoint\s*:)' | Where-Object {$_ -match ('(?m)^Path Group\s*:\s*'+[regex]::Escape($clock)+'\s*$') -and $_ -match '(?m)^Path Type\s*:\s*max ' -and $_ -match '\bSetup time'})
    $uncertainties=@($cpuSetupPaths | ForEach-Object {[regex]::Matches($_,'clock uncertainty\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s*\n\s*Setup time')} | ForEach-Object { [double]::Parse($_.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture) })
    if($uncertainties.Count -lt 2 -or $uncertainties.Count -ne $cpuSetupPaths.Count -or @($uncertainties | Where-Object { [math]::Abs($_+0.150) -gt 0.0001 }).Count -gt 0) {throw 'Final CPU setup paths do not retain 0.150 ns uncertainty.'}
    $physical=($log -split 'Device Utilization Summary :')[-1]
    $resources=[ordered]@{}; $luts=0; $ffs=0
    foreach($block in @('CLMA','CLMS')) {
        $m=[regex]::Match($physical,'\| Use of '+$block+'\s+\|[^\n]+\n\|\s+FF\s+\|\s*(\d+)[^\n]+\n\|\s+LUT\s+\|\s*(\d+)')
        if(-not $m.Success) {throw ('Missing post-route resources: '+$block)}
        $resources[$block]=[ordered]@{ff=[int]$m.Groups[1].Value;lut=[int]$m.Groups[2].Value}; $ffs+=[int]$m.Groups[1].Value; $luts+=[int]$m.Groups[2].Value
    }
    foreach($block in @('DRM','GPLL','APM')) { $m=[regex]::Match($physical,'\| Use of '+$block+'\s+\|\s*([0-9.]+)\s*\|'); if($m.Success) {$resources[$block]=[double]::Parse($m.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)} }
    $resources.post_route_luts=$luts; $resources.post_route_ffs=$ffs
    $summary=[regex]::Match($timing,'Design Summary\s*:\s*([^\r\n]+)').Groups[1].Value.Trim()
    $cornerAudit=Get-CornerAudit $timing
    if($summary -eq 'All Constraints Met.' -and -not $cornerAudit.all_corners_passed){throw 'Global timing summary contradicts corner summary values.'}
    return [ordered]@{clock_hz=$ClockHz;cpu_period_ns=$period;clock_loads=[int]$clocks[0].Groups[2].Value;timing_summary=$summary;constraints_met=($summary -eq 'All Constraints Met.' -and $cornerAudit.all_corners_passed);setup_wns_ns=[double]::Parse($performance[0].Groups[5].Value,[Globalization.CultureInfo]::InvariantCulture);estimated_mhz_not_hardware_measurement=[double]::Parse($performance[0].Groups[2].Value,[Globalization.CultureInfo]::InvariantCulture);setup_uncertainty_ns=0.150;setup_uncertainty_paths_checked=$uncertainties.Count;all_corner_audit=$cornerAudit;resources=$resources;timing_report=$timingPath;timing_report_sha256=(Get-Sha $timingPath);hardware_validated=$false}
}

try {
    if ($PSVersionTable.PSVersion.Major -lt 7) {throw 'PowerShell 7 or newer is required.'}
    $taskRoot=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $workspace=[System.IO.Path]::GetDirectoryName($taskRoot)
    $frozenRelease=[System.IO.Path]::Combine($workspace,'Current_Paper_and_Sub7000_Core_Releases_20261012','cores',$Release)
    $script:SourceInputs=[System.IO.Path]::Combine($frozenRelease,'physical','V0','inputs')
    $recipe=Get-Content -LiteralPath ([System.IO.Path]::Combine($frozenRelease,'recipe.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if (-not $PSBoundParameters.ContainsKey('PlacementSeed')) { $PlacementSeed=[int]([regex]::Match($recipe.roles.V0.pnr_options,'-gplace_seed\s+(\d+)').Groups[1].Value) }
    if ([string]::IsNullOrWhiteSpace($BuildDirectory)) {
        if($Action -eq 'Audit') {throw 'Audit requires an explicit build directory.'}
        $runName=Get-Date -Format 'yyyyMMdd-HHmmss'; $runName+='-'+[guid]::NewGuid().ToString('N').Substring(0,8)
        $script:Build=[System.IO.Path]::Combine($taskRoot,$Release,'builds',$runName)
    } else {$script:Build=[System.IO.Path]::GetFullPath($BuildDirectory)}
    $releaseRoot=[System.IO.Path]::Combine($taskRoot,$Release)
    if(-not $script:Build.StartsWith($releaseRoot+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Build directory must belong to the selected release.'}
    $script:Inputs=[System.IO.Path]::Combine($script:Build,'inputs')
    $manifestPath=[System.IO.Path]::Combine($script:Build,'manifest.json')
    if(-not(Test-Path -LiteralPath $manifestPath)) {
        if($Action -eq 'Audit') {throw 'Prepared build manifest missing.'}
        [void][System.IO.Directory]::CreateDirectory($script:Build)
        $frozenCopy=[System.IO.Path]::Combine($script:Build,'frozen_inputs')
        Copy-Item -LiteralPath $script:SourceInputs -Destination $frozenCopy -Recurse
        Copy-Item -LiteralPath $script:SourceInputs -Destination $script:Inputs -Recurse
        Copy-Item -LiteralPath ([System.IO.Path]::Combine($frozenRelease,'recipe.json')) -Destination ([System.IO.Path]::Combine($script:Build,'recipe.json'))
        $hashes=Get-Inventory $script:SourceInputs
        Write-JsonFile ([System.IO.Path]::Combine($script:Build,'source-hashes.json')) $hashes
        $topPath=[System.IO.Path]::Combine($script:Inputs,'pds_soc_top.v')
        $original=[System.IO.File]::ReadAllText($topPath)
        $pattern='\.INIT_FILE\("[^"]+"\)'
        if([regex]::Matches($original,$pattern).Count -ne 1) {throw 'Expected one top-level firmware binding.'}
        $binding='.INIT_FILE("'+[System.IO.Path]::Combine($script:Inputs,'firmware.hex').Replace([System.IO.Path]::DirectorySeparatorChar,'/')+'")'
        $modified=[regex]::Replace($original,$pattern,$binding)
        [System.IO.File]::WriteAllText($topPath,$modified,$script:Utf8Plain)
        $diff=@('Changed field: pds_soc_top.board.INIT_FILE','--- frozen pds_soc_top.v','+++ relocated inputs/pds_soc_top.v',('- '+[regex]::Match($original,$pattern).Value),('+ '+$binding),'All functional RTL, PLL, constraints, and firmware bytes are identical to the frozen physical V0 inputs.')
        [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($script:Build,'DIFF_FILE.txt'),$diff,$script:Utf8Bom)
        $script:Manifest=[ordered]@{schema='minimal-pipeline-ila/v1';release=$Release;build_directory=$script:Build;source_release=$frozenRelease;configuration='V0';clock_hz=[long]$recipe.clock_hz;placement_seed=$PlacementSeed;clock_uncertainty_ns=0.150;device='PG2L200H';package='FBB676';speedgrade='-6';firmware_sha256=(Get-Sha ([System.IO.Path]::Combine($script:Inputs,'firmware.hex')));stage='prepared';status='prepared';hardware_validated=$false;full_score_qualified=$false;changed_field='pds_soc_top.board.INIT_FILE (path relocation only)';created_utc=[datetime]::UtcNow.ToString('o');updated_utc=$null}
        $script:Manifest.ila_profile=$IlaProfile
        Save-Manifest
        Copy-Item -LiteralPath ([System.IO.Path]::Combine($PSScriptRoot,'Restore-MinimalIlaInputs.ps1')) -Destination ([System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1'))
        $baseline='BASELINE PASS: '+$hashes.Count+' frozen physical input SHA256 values recorded; firmware matches recipe; functional RTL untouched.'
        if($script:Manifest.firmware_sha256 -ne $recipe.roles.V0.firmware_sha256) {throw 'Firmware does not match frozen recipe.'}
        $audit=@(Test-Inputs)
        $rollbackTarget=[System.IO.Path]::Combine($script:Build,'rollback_test','inputs')
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($rollbackTarget))
        Copy-Item -LiteralPath $script:Inputs -Destination $rollbackTarget -Recurse
        $pwsh=[System.IO.Path]::Combine($PSHOME,'pwsh.exe')
        $rollbackScript=[System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1')
        $rollbackResult=@(& $pwsh -NoProfile -File $rollbackScript -BuildDirectory $script:Build -TargetDirectory $rollbackTarget)
        $rollbackExit=$LASTEXITCODE
        if($rollbackExit -ne 0) {throw 'Rollback test failed.'}
        $verification=@(('Changed field: '+$script:Manifest.changed_field),('MODIFIED_FILE='+$topPath),('DIFF_FILE='+[System.IO.Path]::Combine($script:Build,'DIFF_FILE.txt')),('VERIFICATION='+[System.IO.Path]::Combine($script:Build,'VERIFICATION.txt')),('ROLLBACK='+$rollbackScript),('BASELINE command: Build-MinimalIla.ps1 -Release '+$Release+' -Action Prepare'),'BASELINE input: frozen physical/V0/inputs and recipe.json',('BASELINE output: '+$baseline),'BASELINE exit: 0','MODIFIED command: Test-Inputs',('MODIFIED input: '+$script:Inputs),('MODIFIED output: '+($audit -join ' ')),'MODIFIED exit: 0',('ROLLBACK command: pwsh -NoProfile -File "'+$rollbackScript+'" -BuildDirectory "'+$script:Build+'" -TargetDirectory "'+$rollbackTarget+'"'),('ROLLBACK input: '+$rollbackTarget),('ROLLBACK output: '+($rollbackResult -join ' ')),('ROLLBACK exit: '+$rollbackExit),'Restored behavior/status: a separate rollback copy has every frozen hash and original top firmware path. The build inputs retain their relocated firmware binding.','The requested waveform deliverable uses local RTL simulation; no physical board run is part of this task.')
        [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),$verification,$script:Utf8Bom)
        Write-Output $baseline
    } else {
        $script:Manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
        if($script:Manifest.release -ne $Release -or $script:Manifest.placement_seed -ne $PlacementSeed) {throw 'Release or placement seed differs from prepared manifest.'}
        if(-not $script:Manifest.Contains('ila_profile')){$script:Manifest.ila_profile='Shared42'}
        if($script:Manifest.ila_profile -ne $IlaProfile){throw 'ILA profile differs from the prepared manifest.'}
    }
    Write-Output ('BUILD_DIRECTORY='+$script:Build)
    Test-Inputs
    if($Action -eq 'Prepare') {exit 0}
    $synthesis=[System.IO.Path]::Combine($script:Build,'synthesis')
    $implementation=[System.IO.Path]::Combine($script:Build,'implementation')
    if($Action -eq 'Build') {
        $script:Manifest.status='running'
        if($script:Manifest.Contains('error')){$script:Manifest.Remove('error')}
        Save-Manifest
        $script:Mutex=[System.Threading.Mutex]::new($false,'AAAFPGA_PDS2022_MinimalILA')
        Write-Output 'Waiting for the shared PDS implementation mutex.'
        while(-not $script:MutexHeld) {try {$script:MutexHeld=$script:Mutex.WaitOne(15000)} catch [System.Threading.AbandonedMutexException] {$script:MutexHeld=$true}; if(-not $script:MutexHeld) {Write-Output ('WAITING PDS '+[datetime]::UtcNow.ToString('o'))}}
        $active=@(Get-Process -Name 'pds_shell','cdt_ins' -ErrorAction SilentlyContinue)
        if($active.Count -gt 0) {throw ('An external PDS process is active; no processes were stopped. PIDs='+($active.Id -join ','))}
        $pdsBin=[System.IO.Path]::Combine('D:/','PDS_2022.2-SP6.4','bin')
        $pds=[System.IO.Path]::Combine($pdsBin,'pds_shell.exe'); $inserter=[System.IO.Path]::Combine($pdsBin,'cdt_ins.exe')
        foreach($executable in @($pds,$inserter)) {if(-not(Test-Path -LiteralPath $executable -PathType Leaf)){throw ('Vendor executable missing: '+$executable)}}
        if([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) {$env:PANGO_LICENSE_FILE=[Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE','User')}
        if([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) {throw 'PANGO_LICENSE_FILE is not configured.'}
        $constraints=@('board.fdc','uart_remotelab.fdc') | ForEach-Object {'add_constraint '+(Get-TclPath ([System.IO.Path]::Combine($script:Inputs,'constraints',$_)))}
        $architecture='set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676'
        $adfSource=[System.IO.Path]::Combine($synthesis,'synthesize','pds_soc_top_syn.adf')
        $netlistSource=[System.IO.Path]::Combine($synthesis,'synthesize','pds_soc_top_syn.vm')
        if(-not(Test-Path -LiteralPath $adfSource)) {
            [void][System.IO.Directory]::CreateDirectory($synthesis)
            $lines=@(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($script:Inputs,'rtl')) -Filter '*.sv' -File | Sort-Object Name | ForEach-Object {'add_design '+(Get-TclPath $_.FullName)})
            $lines+=@(('add_design '+(Get-TclPath ([System.IO.Path]::Combine($script:Inputs,'pds_soc_top.v')))),('add_design '+(Get-TclPath ([System.IO.Path]::Combine($script:Inputs,'fpga','rv32_pll.sv')))))
            $lines+=$constraints; $lines+=@($architecture,'compile -system_verilog -top_module pds_soc_top','synthesize -ads -selected_syn_tool_opt 2')
            $tcl=[System.IO.Path]::Combine($synthesis,'build.tcl'); Write-Lines $tcl $lines
            $output=Invoke-Vendor $pds @('-file',$tcl,'-work_dir',$synthesis,'-project_name','cpu_ila_synthesis') $synthesis 'pds' 3600
            $output | Write-Output
        }
        $synLog=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($synthesis,'run.log'))
        if($synLog -notmatch 'Executing : synthesize -ads -selected_syn_tool_opt 2 successfully\.' -or -not(Test-Path -LiteralPath $netlistSource)) {throw 'ADS synthesis completion is not proven.'}
        $script:Manifest.stage='synthesized'; Save-Manifest
        if($StopAfterSynthesis) {Write-Output 'SYNTHESIS PASS';exit 0}
        [void][System.IO.Directory]::CreateDirectory($implementation)
        $adf=[System.IO.Path]::Combine($implementation,'source.adf'); $netlistPath=[System.IO.Path]::Combine($implementation,'netlist.v')
        Copy-Item -LiteralPath $adfSource -Destination $adf -Force; Copy-Item -LiteralPath $netlistSource -Destination $netlistPath -Force
        $probeTcl=[System.IO.Path]::Combine($implementation,'probe.tcl')
        Write-Lines $probeTcl @(('ins_new '+(Get-TclPath ([System.IO.Path]::Combine($implementation,'probe.fic')))),('ins_set_file -input '+(Get-TclPath $adf)),'ins_list_nets','exit')
        $probe=Invoke-Vendor $inserter @('-device','PG2L200H','-package','FBB676','-speedgrade','-6','-file',$probeTcl) $implementation 'probe' 600
        $available=@([regex]::Matches($probe,'(?m)^\d+\s*:\s*(\S+)\s+\S+\s*$') | ForEach-Object {$_.Groups[1].Value})
        if($available.Count -lt 100) {throw 'Native inserter net inventory is missing.'}
        $data=[System.Collections.Generic.List[string]]::new(); $mapping=[System.Collections.Generic.List[object]]::new()
        for($i=0;$i -lt 32;$i++) {$native=Resolve-Net ('ex_pc['+$i+']') @('board/soc/core/ex_pc['+$i+']') $available; $data.Add($native);$mapping.Add([ordered]@{channel=$i;meaning=('ex_pc['+$i+']');native=$native})}
        $meaning=@('if_valid','id_valid','ex_valid','mem_valid','wb_valid','id_fire','ex_fire','mem_flush','frontend_fire','mem_fire')
        for($i=0;$i -lt $meaning.Count;$i++) {
            $name=$meaning[$i];$candidates=@('board/soc/core/'+$name)
            if($i -lt 5){$candidates+=@(('board/soc/core/pipeline_valid['+$i+']'),('board/soc/unused_pipeline_valid['+$i+']'));if($i -eq 4){$candidates+=@('board/soc/core/board/unused_trace_valid','board/soc/core/trace_valid','board/soc/unused_trace_valid')}}
            if($name -eq 'frontend_fire'){$candidates+=@('board/soc/core/frontend/fire','board/soc/core/frontend_out_valid_and_ready')}
            $native=Resolve-Net $name $candidates $available; $data.Add($native);$mapping.Add([ordered]@{channel=(32+$i);meaning=$name;native=$native})
        }
        [void](Resolve-Net 'sample clock' @('cpu_clk') $available)
        $shared=($IlaProfile -eq 'Shared42')
        $captureSourceIndices=@(0..41)
        if($IlaProfile -eq 'Lean24') {
            $captureSourceIndices=@(0..15)+@(32,33,34,35,36,37,38,41)
            $fullData=$data.ToArray();$fullMapping=$mapping.ToArray()
            $data=[System.Collections.Generic.List[string]]::new();$mapping=[System.Collections.Generic.List[object]]::new()
            for($i=0;$i -lt $captureSourceIndices.Count;$i++){$sourceIndex=$captureSourceIndices[$i];$data.Add($fullData[$sourceIndex]);$mapping.Add([ordered]@{channel=$i;meaning=$fullMapping[$sourceIndex].meaning;native=$fullData[$sourceIndex];source_expanded_channel=$sourceIndex})}
        }
        $trigger=if($shared){@($data.ToArray())}elseif($IlaProfile -eq 'Lean24'){@($data.ToArray()[0..15])+@($data[22])}else{@($data.ToArray()[0..31])+@($data[38])}
        $fic=[System.IO.Path]::Combine($implementation,'cpu.fic'); New-Fic $adf $data.ToArray() $trigger $fic $shared
        $expected=[System.IO.File]::ReadAllText($fic)
        $verifyTcl=[System.IO.Path]::Combine($implementation,'verify.tcl'); Write-Lines $verifyTcl @(('ins_open '+(Get-TclPath $fic)),'ins_core_info -core 0','ins_core_info -core 0 -trig 0','ins_save','exit')
        $verified=Invoke-Vendor $inserter @('-device','PG2L200H','-package','FBB676','-speedgrade','-6','-file',$verifyTcl) $implementation 'verify' 600
        $canonical=[System.IO.File]::ReadAllText($fic).Replace("`r",'')
        foreach($line in $expected -split '\r?\n' | Where-Object {$_ -match '^Project\.unit<0>\.(dataChannel|dataPortWidth|dataEqualsTrigger|triggerChannel|clockChannel|triggerPortWidth|triggerMatchType|dataDepth)'}) {if(($canonical -split '\n') -cnotcontains $line){throw ('Inserter changed required FIC field: '+$line)}}
        for($i=0;$i -lt $trigger.Count;$i++){if($verified -notmatch ('(?m)^Trigger Channel '+$i+':\s*'+[regex]::Escape($trigger[$i])+'\s*$')){throw ('Native trigger connection unverified: '+$i)}}
        $matchName=if($shared){'BasicWEdges'}else{'Basic'}
        foreach($required in @(('(?m)^Data Same As Trigger:\s*'+[int]$shared+'\s*$'),'(?m)^Data Max Depth:\s*1024\s*$','(?m)^Used As Data Port:\s*1\s*$','(?m)^Clock Port channel:\s*cpu_clk\s*$',('(?m)^Match Type:\s*'+$matchName+'\s*$'))) {if($verified -notmatch $required){throw ('Native capture field unverified: '+$required)}}
        if(-not $shared){for($i=0;$i -lt $data.Count;$i++){if($verified -notmatch ('(?m)^Data Channel '+$i+':\s*'+[regex]::Escape($data[$i])+'\s*$')){throw ('Native data connection unverified: '+$i)}}}
        $netlist=[System.IO.File]::ReadAllText($netlistPath)
        $coreModules=[regex]::Matches($netlist,'\bmodule rv32_core\b(.*?)\bendmodule\b',[System.Text.RegularExpressions.RegexOptions]::Singleline)
        if($coreModules.Count -ne 1){throw 'CPU module missing or ambiguous in synthesized netlist.'}
        $driverProof=[System.Collections.Generic.List[object]]::new()
        for($i=0;$i -lt 5;$i++) {
            $register=$meaning[$i]
            $driver=[regex]::Matches($coreModules[0].Groups[1].Value,'\bGTP_DFF_C\s*/\*\s*'+$register+'\s*\*/\s*#\([^;]*?\)\s*'+$register+'\s*\(\s*\.Q\s*\(([^)]+)\)',[System.Text.RegularExpressions.RegexOptions]::Singleline)
            if($driver.Count -ne 1){throw ('Pipeline register driver missing or ambiguous: '+$register)}
            $q=$driver[0].Groups[1].Value.Trim().TrimStart([char]92)
            $local='board/soc/core/'+$q
            $pipelineIndex=if($IlaProfile -eq 'Lean24'){16+$i}else{32+$i}
            if($data[$pipelineIndex] -cne $local){throw ('Pipeline alias needs explicit proof: '+$data[$pipelineIndex]+' vs '+$local)}
            $driverProof.Add([ordered]@{meaning=$register;primitive='GTP_DFF_C';instance=$register;q=$q;native=$local})
        }
        $mappingRecord=[ordered]@{clock='cpu_clk';depth=1024;profile=$IlaProfile;data_channels=$data.Count;trigger_channels=$trigger.Count;data_equals_trigger=$shared;expanded_observation_channels=42;expanded_observation_source_indices=$captureSourceIndices;expanded_observation_relationship=if($IlaProfile -eq 'Lean24'){'The local 42-bit RTL waveform is a superset. This physical core captures the selected 24 native signals only.'}else{'The local 42-bit RTL waveform and physical capture use the same ordered signal meanings.'};data=$mapping.ToArray();trigger=$trigger;native_net_inventory_count=$available.Count;pipeline_driver_proof=$driverProof.ToArray();source_netlist_sha256=(Get-Sha $netlistPath);fic_sha256=(Get-Sha $fic);verified_by='cdt_ins ins_list_nets + ins_core_info + canonical FIC + synthesized pipeline register Q drivers';sample_alignment='Native signals at the same rising cpu_clk edge; zero extra probe registers; no functional feedback.'}
        Write-JsonFile ([System.IO.Path]::Combine($implementation,'mapping-audit.json')) $mappingRecord
        $script:Manifest.stage='ila_mapping_verified';Save-Manifest
        $pnr=[regex]::Replace($recipe.roles.V0.pnr_options,'-gplace_seed\s+\d+','-gplace_seed '+$PlacementSeed)
        $implTcl=[System.IO.Path]::Combine($implementation,'build.tcl')
        Write-Lines $implTcl (@(('add_design '+(Get-TclPath $netlistPath)))+$constraints+@(('add_fic '+(Get-TclPath $fic)),$architecture,'compile -system_verilog -top_module pds_soc_top',('dev_map -input_db_file '+(Get-TclPath $adf)),('pnr '+$pnr),'report_timing','gen_bit_stream'))
        Write-JsonFile ([System.IO.Path]::Combine($implementation,'input-hashes.json')) (Get-Inventory $script:Inputs)
        $implementationHashes=[ordered]@{}
        foreach($name in @('source.adf','netlist.v','cpu.fic','build.tcl','mapping-audit.json')) {$implementationHashes[$name]=Get-Sha ([System.IO.Path]::Combine($implementation,$name))}
        Write-JsonFile ([System.IO.Path]::Combine($implementation,'implementation-input-hashes.json')) $implementationHashes
        $implOutput=Invoke-Vendor $pds @('-file',$implTcl,'-work_dir',$implementation,'-project_name','cpu_ila') $implementation 'pds' 10800
        $implOutput -split '\r?\n' | Select-Object -Last 30 | Write-Output
    }
    Test-Inputs
    $report=Get-PhysicalReport $implementation $script:Manifest.clock_hz
    $bitstream=[System.IO.Path]::Combine($implementation,'generate_bitstream','pds_soc_top.sbit')
    if(-not(Test-Path -LiteralPath $bitstream -PathType Leaf)) {throw 'Generated ILA bitstream missing.'}
    $invocation=Get-Content -LiteralPath ([System.IO.Path]::Combine($implementation,'pds.invocation.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if($invocation.exit_code -ne 0 -or $invocation.status -ne 'finished') {throw 'Physical vendor invocation is incomplete.'}
    $started=if($invocation.started_utc -is [datetime]){$invocation.started_utc.ToUniversalTime()}else{[datetime]::Parse([string]$invocation.started_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()}
    $finished=if($invocation.finished_utc -is [datetime]){$invocation.finished_utc.ToUniversalTime()}else{[datetime]::Parse([string]$invocation.finished_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()}
    foreach($output in @($bitstream,[System.IO.Path]::Combine($implementation,'report_timing','pds_soc_top.rtr'),[System.IO.Path]::Combine($implementation,'run.log'))) {
        $item=Get-Item -LiteralPath $output
        if($item.Length -lt 1 -or $item.LastWriteTimeUtc -lt $started.AddSeconds(-2) -or $item.LastWriteTimeUtc -gt $finished.AddSeconds(2)) {throw ('Physical output is stale or empty: '+$output)}
    }
    $implementationHashesPath=[System.IO.Path]::Combine($implementation,'implementation-input-hashes.json')
    if(Test-Path -LiteralPath $implementationHashesPath) {
        $implementationHashes=Get-Content -LiteralPath $implementationHashesPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
        foreach($name in $implementationHashes.Keys) {if((Get-Sha ([System.IO.Path]::Combine($implementation,$name))) -ne $implementationHashes[$name]){throw ('Physical input hash changed: '+$name)}}
    }
    $script:Manifest.report=$report;$script:Manifest.bitstream=$bitstream;$script:Manifest.bitstream_sha256=Get-Sha $bitstream;$script:Manifest.fic=[System.IO.Path]::Combine($implementation,'cpu.fic');$script:Manifest.fic_sha256=Get-Sha $script:Manifest.fic
    $script:Manifest.stage='implemented';$script:Manifest.status=if($report.constraints_met){'internal_timing_passed'}else{'timing_failed'}
    if($script:Manifest.Contains('error')){$script:Manifest.Remove('error')}
    Save-Manifest
    Write-JsonFile ([System.IO.Path]::Combine($implementation,'resource-timing-summary.json')) $report
    $validation=@('MODIFIED PHYSICAL command: pds_shell.exe -file implementation/build.tcl -work_dir implementation -project_name cpu_ila',('MODIFIED PHYSICAL input: '+$script:Build),('MODIFIED PHYSICAL result: '+$script:Manifest.status+'; WNS='+$report.setup_wns_ns+' ns; LUT='+$report.resources.post_route_luts+'; FF='+$report.resources.post_route_ffs+'; bitstream SHA256='+$script:Manifest.bitstream_sha256),'MODIFIED PHYSICAL vendor exit: 0','Restored behavior/status: rollback_test remains byte-identical to frozen baseline; modified build remains instrumented; local RTL waveform and full CoreMark simulation evidence are tracked separately.')
    [System.IO.File]::AppendAllLines([System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),[string[]]$validation,$script:Utf8Bom)
    foreach($artifact in @([System.IO.Path]::Combine($script:Inputs,'pds_soc_top.v'),[System.IO.Path]::Combine($script:Build,'DIFF_FILE.txt'),[System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),[System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1'),$manifestPath,$bitstream,$script:Manifest.fic)) {[void][System.IO.File]::ReadAllBytes($artifact)}
    Write-Output ($script:Manifest|ConvertTo-Json -Depth 32)
    if(-not $report.constraints_met){exit 2}
    exit 0
} catch {
    if($null -ne $script:Manifest){$script:Manifest.status='failed';$script:Manifest.error=$_.Exception.Message;Save-Manifest}
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    if($script:MutexHeld -and $null -ne $script:Mutex){$script:Mutex.ReleaseMutex()}
    if($null -ne $script:Mutex){$script:Mutex.Dispose()}
}
