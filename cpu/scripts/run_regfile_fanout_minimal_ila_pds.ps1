param([ValidateRange(0,2147483647)][int]$PlacementSeed = 2)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $project = [IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot, '..'))
    $pds = [IO.Path]::Combine('D:/', 'PDS_2022.2-SP6.4')
    $Profile = 'RegfileFanout157500Minimal'
    $source = [IO.Path]::Combine($project, 'build', 'regfile-valid-fanout-stage', 'build', 'pds', '20260909-124605-a402f7e8')
    if (@(Get-Process -Name 'pds*' -ErrorAction SilentlyContinue).Count) { throw 'Another PDS implementation is live' }
    $auditLog = [IO.Path]::Combine($project, 'build', 'regfile-fanout-minimal-ila-source-audit.log')
    & wsl.exe --exec python3 /mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu/build/audit_regfile_fanout_minimal_ila_source.py *> $auditLog
    if ($LASTEXITCODE -ne 0) { throw 'Actual synthesis input and ILA mapping audit failed' }
    $manifestPath = [IO.Path]::Combine($project, 'build', 'regfile-fanout-minimal-ila-source-candidate.json')
    $original = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($original.Profile -ne $Profile -or $original.SourceTimingConstraintsMet -or $original.SourceAcceptedManifest -or $original.ClockHz -ne 157500000) { throw 'Input is not the explicitly audited experimental synthesis candidate' }
    $existing = [IO.Path]::Combine($project, 'build', 'ila')
    foreach ($directory in Get-ChildItem -LiteralPath $existing -Directory) {
        $input = [IO.Path]::Combine($directory.FullName, 'source-candidate.json')
        if (Test-Path -LiteralPath $input) {
            $prior = Get-Content -LiteralPath $input -Raw -Encoding utf8 | ConvertFrom-Json
            if ($prior.Profile -eq $Profile -and $prior.SourceNetlistSha256 -eq $original.SourceNetlistSha256) { throw 'This source insertion already started; inspect actual process and outputs' }
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
    Copy-Item -LiteralPath $manifestPath -Destination ([System.IO.Path]::Combine($build, 'source-candidate.json'))
    $fic = [System.IO.Path]::Combine($build, 'cpu.fic')
    $templateName = 'cpu_ila_regfilefanout157500_minimal.fic.in'
    $ficTemplate = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, $templateName))
    $ficText = $ficTemplate.Replace('__SOURCE_ADF__', $adf.Replace([System.IO.Path]::DirectorySeparatorChar, '/'))
    [System.IO.File]::WriteAllText($fic, $ficText, $utf8)
    $verify = [System.IO.Path]::Combine($build, 'verify_fic.tcl')
    $ficTcl = $fic.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    [System.IO.File]::WriteAllLines($verify, @("ins_open {$ficTcl}", 'ins_core_info -core 0', 'ins_core_info -core 0 -trig 0', 'ins_save', 'exit'), $utf8)
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
    $canonical = [System.IO.File]::ReadAllText($fic).Replace("`r", "")
    $expectedConnections = @($ficText -split '\r?\n' | Where-Object { $_ -match '^Project\.unit<0>\.(dataChannel|dataPortWidth|dataEqualsTrigger|triggerChannel|clockChannel|triggerPortWidth|triggerMatchType|dataDepth)' })
    foreach ($connection in $expectedConnections) {
        if (($canonical -split '\r?\n') -cnotcontains $connection) { throw "Inserter changed or removed a required connection: $connection" }
    }
    if ([regex]::Matches($canonical, '(?m)^Project\.unit<0>\.triggerChannel<0><').Count -ne 33 -or [regex]::Matches($canonical, '(?m)^Project\.unit<0>\.dataChannel<').Count -ne 42) { throw 'Copied split capture or trigger width changed' }
    $ficWsl = '/mnt/d/' + $fic.Replace([IO.Path]::DirectorySeparatorChar, '/').Substring(3)
    $verifyWsl = '/mnt/d/' + $verifyOut.Replace([IO.Path]::DirectorySeparatorChar, '/').Substring(3)
    & wsl.exe --exec python3 /mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu/build/audit_regfile_fanout_minimal_ila_source.py --fic $ficWsl --verify-log $verifyWsl
    if ($LASTEXITCODE -ne 0) { throw 'Copied split FIC actual channel validation failed' }
    for ($channel = 0; $channel -lt 33; $channel++) {
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
        SourceTimingConstraintsMet = $false; SourceAcceptedManifest = $false; FullScoreQualified = $false
        SourceSnapshot = $original.SourceSnapshot
        Profile = $Profile; SourceCandidateSha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash
        SampleClockNet = if ($Profile -ne 'Legacy27') { 'cpu_clk' } else { 'nt_clk' }
        Channel39Meaning = 'mem_flush'; Channel40Meaning = 'fetch_complete'; Channel41Meaning = 'mem_fire'
        BuildDirectory = $build; SourceBuild = $source; Device = $original.Device; ClockHz = $original.ClockHz
        SourceAdfSha256 = (Get-FileHash -LiteralPath $adf -Algorithm SHA256).Hash
        SourceNetlistSha256 = (Get-FileHash -LiteralPath $netlist -Algorithm SHA256).Hash
        FirmwareSha256 = $firmwareHash; Bitstream = $bitstream; BitstreamSha256 = (Get-FileHash -LiteralPath $bitstream -Algorithm SHA256).Hash
        Fic = $fic; FicSha256 = (Get-FileHash -LiteralPath $fic -Algorithm SHA256).Hash
        TriggerChannels = 33; DataEqualsTrigger = $false; TriggerMatchType = 0
        CaptureChannels = 42; CaptureDepth = 1024; TimingConstraintsMet = $true; TimingReport = $timingPath
        ResourceReport = [System.IO.Path]::Combine($build, 'device_map', 'pds_soc_top.dmr')
        HardwareValidated = $false; GeneratedUtc = [datetime]::UtcNow.ToString('o')
    }
    $result | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, 'manifest.json')) -Encoding utf8BOM
    Write-Output ($result | ConvertTo-Json -Depth 20)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
