param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$SourceBuild,
    [ValidateSet('Legacy27', 'Target120', 'Target132Carry', 'Target132Kept')][string]$Profile = 'Legacy27',
    [ValidateNotNullOrEmpty()][string]$PdsRoot = 'D:/PDS_2022.2-SP6.4',
    [ValidateRange(0,2147483647)][int]$PlacementSeed = 0
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $source = (Resolve-Path -LiteralPath $SourceBuild).Path
    $pds = (Resolve-Path -LiteralPath $PdsRoot).Path
    $manifestPath = [System.IO.Path]::Combine($source, 'manifest.json')
    $original = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($Profile -eq 'Legacy27') {
    if ($original.PSObject.Properties.Name -contains 'EnableM' -and $original.EnableM -eq 1) { throw 'The existing ILA net map has not been validated for the M extension.' }
    if ($original.PSObject.Properties.Name -contains 'FetchOverlap' -and $original.FetchOverlap -eq 1) { throw 'The existing ILA net map has not been validated for overlapping fetch.' }
    if ($original.PSObject.Properties.Name -contains 'FastDCacheRead' -and $original.FastDCacheRead -eq 1) { throw 'The existing ILA net map has not been validated for early D-cache reads.' }
    if ($original.PSObject.Properties.Name -contains 'ICacheSetBits' -and $original.ICacheSetBits -ne $original.CacheSetBits) { throw 'The existing ILA net map has not been validated for asymmetric cache geometry.' }
    if ($original.PSObject.Properties.Name -contains 'FastDCacheWrite' -and $original.FastDCacheWrite -eq 1) { throw 'The existing ILA net map has not been validated for early D-cache writes.' }
    if ($original.PSObject.Properties.Name -contains 'EarlyDRequest' -and $original.EarlyDRequest -eq 1) { throw 'The existing ILA net map has not been validated for EX-stage memory requests.' }
    if ($original.PSObject.Properties.Name -contains 'BtbIndexBits' -and $original.BtbIndexBits -ne 4) { throw 'The existing ILA net map has not been validated for this BTB capacity.' }
    if ($original.PSObject.Properties.Name -contains 'DataOverlap' -and $original.DataOverlap -eq 1) { throw 'The existing ILA net map has not been validated for data request overlap.' }
    if ($original.PSObject.Properties.Name -contains 'FastICacheHit' -and $original.FastICacheHit -ne 0) {
        throw 'ILA net map has not been validated for early I-cache response.'
    }
    if ($original.PSObject.Properties.Name -contains 'LoadUseBubble' -and $original.LoadUseBubble -ne 0) {
        throw 'ILA net map has not been validated for registered-load forwarding.'
    }
    if ($original.Device -ne 'PG2L200H-6FBB676' -or $original.ClockHz -ne 27000000 -or $original.CacheEnabled -ne 1 -or $original.Predictor -ne 1 -or $original.UartProfile -ne 'RemoteLab' -or -not $original.TimingConstraintsMet) {
        throw 'ILA net map requires the verified 27 MHz cached/predictor-on RemoteLab design.'
    }
    } else {
        $profileClockHz = if ($Profile -in @('Target132Carry', 'Target132Kept')) { 132000000 } else { 120000000 }
        $required = [ordered]@{ Device='PG2L200H-6FBB676'; ClockHz=$profileClockHz; CacheEnabled=1; Predictor=1; UartProfile='RemoteLab'; UartBaud=115200; EnableM=1; FetchOverlap=1; FastDCacheRead=1; FastDCacheWrite=1; ICacheSetBits=8; CacheSetBits=6; EarlyDRequest=1; BtbIndexBits=8; DataOverlap=1; FastICacheHit=1; LoadUseBubble=0; TimingConstraintsMet=$true }
        foreach ($name in $required.Keys) {
            if ($original.PSObject.Properties.Name -notcontains $name -or $original.$name -ne $required[$name]) { throw "$Profile ILA configuration mismatch: $name" }
        }
        if ($original.PSObject.Properties.Name -notcontains 'SourceSnapshot') { throw "$Profile requires source snapshots." }
        $sourceLockName = switch ($Profile) {
            'Target132Carry' { 'ila_target132_carry_sources.json' }
            'Target132Kept' { 'ila_target132_kept_sources.json' }
            default { 'ila_target120_sources.json' }
        }
        $sourceLockPath = [System.IO.Path]::Combine($PSScriptRoot, $sourceLockName)
        $sourceLock = Get-Content -LiteralPath $sourceLockPath -Raw | ConvertFrom-Json
        $expectedNames = @($sourceLock.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
        $actualNames = @($original.SourceSnapshot.Files.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
        if ($expectedNames.Count -ne 20 -or ($actualNames -join '|') -cne ($expectedNames -join '|')) { throw "$Profile source map is incomplete or unsupported." }
        foreach ($name in $expectedNames) {
            if ($original.SourceSnapshot.Files.$name -cne $sourceLock.$name) { throw "$Profile source revision requires ILA remapping: $name" }
        }
        $snapshotRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($source, 'source'))
        foreach ($entry in $original.SourceSnapshot.Files.PSObject.Properties) {
            $inputPath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($snapshotRoot, $entry.Name))
            if (-not $inputPath.StartsWith($snapshotRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Source snapshot path escapes build.' }
            if ((Get-FileHash -LiteralPath $inputPath -Algorithm SHA256).Hash -ne $entry.Value) { throw "Source snapshot mismatch: $($entry.Name)" }
        }
    }
    $sourceAdf = [System.IO.Path]::Combine($source, 'synthesize', 'pds_soc_top_syn.adf')
    $sourceNetlist = [System.IO.Path]::Combine($source, 'synthesize', 'pds_soc_top_syn.vm')
    $sourceFirmware = [System.IO.Path]::Combine($source, 'firmware.hex')
    $inserter = [System.IO.Path]::Combine($pds, 'bin', 'cdt_ins.exe')
    $shell = [System.IO.Path]::Combine($pds, 'bin', 'pds_shell.exe')
    foreach ($path in @($sourceAdf, $sourceNetlist, $sourceFirmware, $inserter, $shell)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    $firmwareHash = (Get-FileHash -LiteralPath $sourceFirmware -Algorithm SHA256).Hash
    if ($firmwareHash -ne $original.FirmwareSha256) { throw 'Source firmware differs from its build manifest.' }
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) { throw 'PANGO_LICENSE_FILE is not configured.' }
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $build = [System.IO.Path]::Combine($project, 'build', 'ila', $runName)
    foreach ($path in @($project, $source, $build)) {
        if ($path -match '[{}"$;\r\n]') { throw 'Path contains characters unsafe for generated Tcl.' }
    }
    [void](New-Item -ItemType Directory -Path $build)
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $adf = [System.IO.Path]::Combine($build, 'source.adf')
    $netlist = [System.IO.Path]::Combine($build, 'netlist.v')
    Copy-Item -LiteralPath $sourceAdf -Destination $adf
    Copy-Item -LiteralPath $sourceNetlist -Destination $netlist
    Copy-Item -LiteralPath $sourceFirmware -Destination ([System.IO.Path]::Combine($build, 'firmware.hex'))
    Copy-Item -LiteralPath $manifestPath -Destination ([System.IO.Path]::Combine($build, 'source-manifest.json'))
    $fic = [System.IO.Path]::Combine($build, 'cpu.fic')
    $templateName = switch ($Profile) {
        'Target132Carry' { 'cpu_ila_target132_carry.fic.in' }
        'Target132Kept' { 'cpu_ila_target132_kept.fic.in' }
        'Target120' { 'cpu_ila_target120.fic.in' }
        default { 'cpu_ila.fic.in' }
    }
    $ficTemplate = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, $templateName))
    $ficText = $ficTemplate.Replace('__SOURCE_ADF__', $adf.Replace([System.IO.Path]::DirectorySeparatorChar, '/'))
    [System.IO.File]::WriteAllText($fic, $ficText, $utf8)
    $verify = [System.IO.Path]::Combine($build, 'verify_fic.tcl')
    $ficTcl = $fic.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    [System.IO.File]::WriteAllLines($verify, @("ins_open {$ficTcl}", 'ins_core_info -core 0 -trig 0', 'ins_save', 'exit'), $utf8)
    $verifyOut = [System.IO.Path]::Combine($build, 'verify.stdout.txt')
    $verifyErr = [System.IO.Path]::Combine($build, 'verify.stderr.txt')
    $verifyArgument = $verify.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    $process = Start-Process -FilePath $inserter -ArgumentList @('-device', 'PG2L200H', '-package', 'FBB676', '-speedgrade', '-6', '-file', ('"' + $verifyArgument + '"')) -PassThru -WindowStyle Hidden -WorkingDirectory $build -RedirectStandardOutput $verifyOut -RedirectStandardError $verifyErr
    Write-Output "ILA net validation PID: $($process.Id); build: $build"
    if (-not $process.WaitForExit(180000)) {
        $process.Kill()
        $process.WaitForExit()
        throw 'Inserter timed out; only the process started by this script was stopped.'
    }
    $verifyLog = [System.IO.File]::ReadAllText($verifyOut) + [System.IO.File]::ReadAllText($verifyErr)
    if ($process.ExitCode -ne 0 -or $verifyLog -match '(?im)^\s*(E:|Error:)' ) { throw 'Inserter verification failed; inspect its logs.' }
    $canonical = [System.IO.File]::ReadAllText($fic)
    $expectedConnections = @($ficText -split '\r?\n' | Where-Object { $_ -match '^Project\.unit<0>\.(triggerChannel|clockChannel|triggerPortWidth|dataDepth)' })
    foreach ($connection in $expectedConnections) {
        if (($canonical -split '\r?\n') -cnotcontains $connection) { throw "Inserter changed or removed a required connection: $connection" }
    }
    if ([regex]::Matches($canonical, '(?m)^Project\.unit<0>\.triggerChannel<0><\d+>=').Count -ne 109) { throw 'ILA channel count differs from 109.' }
    for ($channel = 0; $channel -lt 109; $channel++) {
        $connection = $expectedConnections | Where-Object { $_.StartsWith("Project.unit<0>.triggerChannel<0><$channel>=") }
        $netName = ($connection -split '=', 2)[1]
        $pattern = '(?m)^Trigger Channel ' + $channel + ':\s*' + [regex]::Escape($netName) + '\s*$'
        if ($verifyLog -notmatch $pattern) { throw "Inserter did not confirm channel $channel." }
    }
    $constraintRoot = if ($original.PSObject.Properties.Name -contains 'SourceSnapshot') {
        [System.IO.Path]::Combine($source, 'source', 'constraints')
    } else { [System.IO.Path]::Combine($project, 'constraints') }
    $boardConstraint = [System.IO.Path]::Combine($build, 'board.fdc')
    $uartConstraint = [System.IO.Path]::Combine($build, 'uart_remotelab.fdc')
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($constraintRoot, 'board.fdc')) -Destination $boardConstraint
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($constraintRoot, 'uart_remotelab.fdc')) -Destination $uartConstraint
    $placement = [ordered]@{ Schema = 1; Seed = $null; Command = 'pnr' }
    if ($PSBoundParameters.ContainsKey('PlacementSeed')) {
        $placement['Seed'] = $PlacementSeed
        $placement['Command'] = 'pnr -gplace_seed ' + $PlacementSeed.ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    $placement | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, 'placement.json')) -Encoding utf8BOM
    $commands = @(
        "add_design {$netlist}", "add_constraint {$boardConstraint}", "add_constraint {$uartConstraint}", "add_fic {$fic}",
        'set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676',
        'compile -system_verilog -top_module pds_soc_top', "dev_map -input_db_file {$adf}", $placement.Command, 'report_timing', 'gen_bit_stream'
    ) | ForEach-Object { $_.Replace([System.IO.Path]::DirectorySeparatorChar, '/') }
    $script = [System.IO.Path]::Combine($build, 'build.tcl')
    [System.IO.File]::WriteAllLines($script, $commands, $utf8)
    $stdout = [System.IO.Path]::Combine($build, 'pds.stdout.log')
    $stderr = [System.IO.Path]::Combine($build, 'pds.stderr.log')
    $started = [datetime]::UtcNow
    $process = Start-Process -FilePath $shell -ArgumentList @('-file', ('"' + $script + '"'), '-work_dir', ('"' + $build + '"'), '-project_name', 'cpu_ila') -PassThru -WindowStyle Hidden -WorkingDirectory $build -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output "PDS ILA PID: $($process.Id)"
    if (-not $process.WaitForExit(1800000)) {
        $process.Kill()
        $process.WaitForExit()
        throw 'PDS timed out; inspect logs and any remaining vendor child processes.'
    }
    $logs = [System.IO.File]::ReadAllText($stdout) + [System.IO.File]::ReadAllText($stderr)
    $logs -split "`n" | Select-Object -Last 20 | Write-Output
    if ($process.ExitCode -ne 0 -or $logs -match '(?m)^E:') { throw 'PDS ILA implementation failed.' }
    $bitstream = [System.IO.Path]::Combine($build, 'generate_bitstream', 'pds_soc_top.sbit')
    if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) { throw 'ILA bitstream missing.' }
    if ((Get-Item -LiteralPath $bitstream).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'ILA bitstream is stale.' }
    $timingPath = [System.IO.Path]::Combine($build, 'report_timing', 'pds_soc_top.rtr')
    $timing = [System.IO.File]::ReadAllText($timingPath)
    if ($timing -notmatch 'Design Summary\s*:\s*All Constraints Met\.') { throw 'ILA timing constraints failed.' }
    if ($Profile -ne 'Legacy27') {
        $clockMatches = [regex]::Matches($timing, '(?m)^\s*clk\|multiplied_clock\.clock_source/pll/CLKOUT0_Inferred\s+([0-9.]+)\s+\{[^}]+\}\s+Generated \(clk\)\s+(\d+)')
        if ($clockMatches.Count -ne 1) { throw 'ILA CPU generated clock missing or ambiguous.' }
        $period = [double]::Parse($clockMatches[0].Groups[1].Value, [System.Globalization.CultureInfo]::InvariantCulture)
        if ([math]::Abs($period - 1e9 / $original.ClockHz) -gt 0.005 -or [int]$clockMatches[0].Groups[2].Value -lt 1) { throw 'ILA CPU clock period or loads mismatch.' }
    }
    $result = [ordered]@{
        Placement = $placement
        Profile = $Profile; SourceManifestSha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
        SampleClockNet = if ($Profile -ne 'Legacy27') { 'cpu_clk' } else { 'nt_clk' }
        Channel106Meaning = if ($Profile -ne 'Legacy27') { 'fetch_complete' } else { 'i_response_valid' }
        Channel107Meaning = if ($Profile -in @('Target132Carry', 'Target132Kept')) { 'mem_fire' } else { 'd_response_valid' }
        BuildDirectory = $build; SourceBuild = $source; Device = $original.Device; ClockHz = $original.ClockHz
        SourceAdfSha256 = (Get-FileHash -LiteralPath $adf -Algorithm SHA256).Hash
        SourceNetlistSha256 = (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash
        FirmwareSha256 = $firmwareHash; Bitstream = $bitstream; BitstreamSha256 = (Get-FileHash -LiteralPath $bitstream -Algorithm SHA256).Hash
        Fic = $fic; FicSha256 = (Get-FileHash -LiteralPath $fic -Algorithm SHA256).Hash
        CaptureChannels = 109; CaptureDepth = 1024; TimingConstraintsMet = $true; TimingReport = $timingPath
        ResourceReport = [System.IO.Path]::Combine($build, 'device_map', 'pds_soc_top.dmr')
        HardwareValidated = $false; GeneratedUtc = [datetime]::UtcNow.ToString('o')
    }
    $result | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, 'manifest.json')) -Encoding utf8BOM
    Write-Output ($result | ConvertTo-Json)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
