param([ValidateRange(0,10)][int]$ICacheSetBits = 0, [ValidateRange(0,1)][int]$DataOverlap = 0, [ValidateRange(1,8)][int]$BtbIndexBits = 4, [ValidateRange(0,1)][int]$EarlyDRequest = 0, [ValidateRange(0,1)][int]$FastDCacheWrite = 0, [ValidateRange(0,1)][int]$FastDCacheRead = 0, [ValidateRange(0,1)][int]$FetchOverlap = 0, [ValidateRange(0,1)][int]$EnableM = 0, [ValidateRange(0,1)][int]$FastICacheHit = 0, [ValidateRange(0,1)][int]$LoadUseBubble = 0, [ValidateSet('Board', 'RemoteLab')][string]$UartProfile = 'Board', [string]$FirmwareHex = '', [ValidateRange(0,1)][int]$Predictor = 1, [ValidateRange(1,8)][int]$CacheSetBits = 4, [ValidateRange(0,1)][int]$CacheEnabled = 1, [ValidateSet(9600,19200,38400,57600,115200)][int]$UartBaud = 115200, [ValidateSet(27000000,54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,120000000,126000000,132000000,135000000,141750000,144000000,146250000,148500000,151200000,153000000,154285714,157500000,162000000,180000000,194400000,216000000,270000000)][int]$ClockHz = 27000000, [ValidateRange(0,2147483647)][int]$PlacementSeed = 0)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    if ([string]::IsNullOrWhiteSpace($FirmwareHex)) {
        & ([System.IO.Path]::Combine($PSScriptRoot, 'build_soc.ps1')) -ExternalUart:($UartProfile -eq 'RemoteLab')
        if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
        $firmwareSource = [System.IO.Path]::Combine($project, 'build', 'soc_selftest.hex')
    } else {
        $firmwareSource = [System.IO.Path]::GetFullPath($FirmwareHex)
        if (-not (Test-Path -LiteralPath $firmwareSource -PathType Leaf)) { throw 'Specified firmware does not exist.' }
        $words = [System.IO.File]::ReadAllLines($firmwareSource)
        if ($words.Count -ne 16384 -or @($words | Where-Object { $_ -notmatch '^[0-9a-fA-F]{8}$' }).Count -ne 0) { throw 'Firmware must be exactly 16384 eight-digit hexadecimal words.' }
        $firmwareManifestPath = [System.IO.Path]::ChangeExtension($firmwareSource, '.build.json')
        if (Test-Path -LiteralPath $firmwareManifestPath -PathType Leaf) {
            $firmwareManifest = Get-Content -LiteralPath $firmwareManifestPath -Raw | ConvertFrom-Json
            if ($firmwareManifest.EnableM -eq 1 -and -not $EnableM) { throw 'RV32IM firmware requires an M-enabled CPU.' }
            if ($firmwareManifest.ClockHz -ne $ClockHz -or $firmwareManifest.HexSha256 -ne (Get-FileHash -LiteralPath $firmwareSource -Algorithm SHA256).Hash) { throw 'Firmware clock or checksum does not match the requested hardware build.' }
        } elseif ($ClockHz -ne 27000000) {
            throw 'Non-default clock firmware requires a matching .build.json manifest.'
        }
    }
    $pdsRoot = [Environment]::GetEnvironmentVariable('PDS_ROOT', 'Process')
    if ([string]::IsNullOrWhiteSpace($pdsRoot)) { $pdsRoot = [System.IO.Path]::Combine('D:/', 'PDS_2022.2-SP6.4') }
    $pdsShell = [System.IO.Path]::Combine($pdsRoot, 'bin', 'pds_shell.exe')
    if (-not (Test-Path -LiteralPath $pdsShell -PathType Leaf)) { throw 'PDS executable missing.' }
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) { throw 'PANGO_LICENSE_FILE is not configured.' }
    $runName = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0, 8))
    $buildRoot = [System.IO.Path]::Combine($project, 'build', 'pds', $runName)
    [void](New-Item -ItemType Directory -Path $buildRoot -Force)
    $sourceRoot = [System.IO.Path]::Combine($buildRoot, 'source')
    $sourceHashes = [ordered]@{}
    foreach ($directory in @('rtl', 'constraints', 'fpga')) {
        $inputDirectory = [System.IO.Path]::Combine($project, $directory)
        $outputDirectory = [System.IO.Path]::Combine($sourceRoot, $directory)
        [void](New-Item -ItemType Directory -Path $outputDirectory -Force)
        $extension = if ($directory -eq 'constraints') { '*.fdc' } else { '*.sv' }
        $inputs = @(Get-ChildItem -LiteralPath $inputDirectory -Filter $extension -File | Sort-Object Name)
        if ($inputs.Count -eq 0) { throw "No PDS source inputs found in $directory" }
        foreach ($inputFile in $inputs) {
            $snapshotFile = [System.IO.Path]::Combine($outputDirectory, $inputFile.Name)
            Copy-Item -LiteralPath $inputFile.FullName -Destination $snapshotFile
            $relative = [System.IO.Path]::GetRelativePath($sourceRoot, $snapshotFile).Replace([System.IO.Path]::DirectorySeparatorChar, '/')
            $sourceHashes[$relative] = (Get-FileHash -LiteralPath $snapshotFile -Algorithm SHA256).Hash
        }
    }
    $sourceSnapshot = [ordered]@{ Schema = 1; Root = $sourceRoot; Files = $sourceHashes }
    $sourceSnapshot | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($buildRoot, 'source-snapshot.json')) -Encoding utf8BOM
    $firmware = [System.IO.Path]::Combine($buildRoot, 'firmware.hex')
    Copy-Item -LiteralPath $firmwareSource -Destination $firmware
    foreach ($path in @($project, $sourceRoot, $buildRoot, $firmware)) {
        if ($path -match '[{}"$;\r\n]') { throw 'Path contains characters unsafe for the generated Tcl or Verilog literal.' }
    }
    $projectTcl = $sourceRoot.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    $buildTcl = $buildRoot.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    $firmwareTcl = $firmware.Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    $template = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, 'build_pds.tcl'))
    $scriptPath = [System.IO.Path]::Combine($buildRoot, 'build.tcl')
    $clockDesign = if ($ClockHz -eq 27000000) { '' } else { 'add_design "' + $projectTcl + '/fpga/rv32_pll.sv"' }
    $template = $template.Replace('__CLOCK_DESIGN__', $clockDesign)
    $placement = [ordered]@{ Schema = 1; Seed = $null; Command = 'pnr' }
    if ($PSBoundParameters.ContainsKey('PlacementSeed')) {
        $placement['Seed'] = $PlacementSeed
        $placement['Command'] = 'pnr -gplace_seed ' + $PlacementSeed.ToString([System.Globalization.CultureInfo]::InvariantCulture)
    }
    if ([regex]::Matches($template, '__PNR_COMMAND__').Count -ne 1) { throw 'Expected one PDS placement command placeholder.' }
    $template = $template.Replace('__PNR_COMMAND__', $placement.Command)
    $placement | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($buildRoot, 'placement-config.json')) -Encoding utf8BOM
    $uartConstraint = if ($UartProfile -eq 'RemoteLab') { 'uart_remotelab.fdc' } else { 'uart_board.fdc' }
    [System.IO.File]::WriteAllText($scriptPath, $template.Replace('__PROJECT_ROOT__', $projectTcl).Replace('__BUILD_ROOT__', $buildTcl).Replace('__UART_CONSTRAINT__', $uartConstraint), [System.Text.UTF8Encoding]::new($false))
    $top = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, 'pds_soc_top.v.in'))
    $top = $top.Replace('__ICACHE_SET_BITS__', [string]$ICacheSetBits)
    $top = $top.Replace('__CLOCK_HZ__', [string]$ClockHz)
    $top = $top.Replace('__LOAD_USE_BUBBLE__', [string]$LoadUseBubble)
    $top = $top.Replace('__FAST_ICACHE_HIT__', [string]$FastICacheHit)
    $top = $top.Replace('__FETCH_OVERLAP__', [string]$FetchOverlap)
    $top = $top.Replace('__FAST_DCACHE_READ__', [string]$FastDCacheRead)
    $top = $top.Replace('__FAST_DCACHE_WRITE__', [string]$FastDCacheWrite)
    $top = $top.Replace('__EARLY_D_REQUEST__', [string]$EarlyDRequest)
    $top = $top.Replace('__BTB_INDEX_BITS__', [string]$BtbIndexBits)
    $top = $top.Replace('__DATA_OVERLAP__', [string]$DataOverlap)
    $top = $top.Replace('__ENABLE_M__', [string]$EnableM)
    $top = $top.Replace('__FIRMWARE_HEX__', $firmwareTcl).Replace('__PREDICTOR__', [string]$Predictor).Replace('__CACHE_SET_BITS__', [string]$CacheSetBits).Replace('__UART_BAUD__', [string]$UartBaud).Replace('__ENABLE_CACHE__', [string]$CacheEnabled)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($buildRoot, 'pds_soc_top.v'), $top, [System.Text.UTF8Encoding]::new($false))
    $stdout = [System.IO.Path]::Combine($buildRoot, 'pds.stdout.log')
    $stderr = [System.IO.Path]::Combine($buildRoot, 'pds.stderr.log')
    $arguments = @('-file', ('"' + $scriptPath + '"'), '-work_dir', ('"' + $buildRoot + '"'), '-project_name', 'zgtc_rv32i')
    $started = [datetime]::UtcNow
    $process = Start-Process -FilePath $pdsShell -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Write-Output "PDS PID: $($process.Id)"
    Write-Output "PDS build directory: $buildRoot"
    $process.WaitForExit()
    $outputText = [System.IO.File]::ReadAllText($stdout) + [System.IO.File]::ReadAllText($stderr)
    $outputText -split "`n" | Select-Object -Last 35 | Write-Output
    if ($process.ExitCode -ne 0 -or $outputText -match '(?m)^E:') { throw 'PDS reported failure; inspect the build logs.' }
    $bitstream = [System.IO.Path]::Combine($buildRoot, 'generate_bitstream', 'pds_soc_top.sbit')
    if (-not (Test-Path -LiteralPath $bitstream -PathType Leaf)) { throw 'PDS did not produce the expected bitstream.' }
    if ((Get-Item -LiteralPath $bitstream).LastWriteTimeUtc -lt $started.AddSeconds(-1)) { throw 'Bitstream is stale.' }
    $manifest = [ordered]@{ BuildDirectory = $buildRoot; Bitstream = $bitstream; BitstreamSha256 = (Get-FileHash -LiteralPath $bitstream -Algorithm SHA256).Hash; FirmwareSha256 = (Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash; Device = 'PG2L200H-6FBB676'; ClockHz = 27000000; GeneratedUtc = [datetime]::UtcNow.ToString('o') }
    $timingPath = [System.IO.Path]::Combine($buildRoot, 'report_timing', 'pds_soc_top.rtr')
    $timingText = [System.IO.File]::ReadAllText($timingPath)
    $reportParser=[System.IO.Path]::Combine($PSScriptRoot,'pds_report.py')
    $resourceSummaryPath=[System.IO.Path]::Combine($buildRoot,'resource-summary.json')
    # Native Windows Python runs the pure-Python audit directly on the build paths (no WSL).
    & python $reportParser --timing $timingPath --log $stdout --clock-hz $ClockHz --json $resourceSummaryPath
    if($LASTEXITCODE) { throw 'PDS timing/resource audit rejected this implementation.' }
    $resourceSummary=Get-Content -LiteralPath $resourceSummaryPath -Raw | ConvertFrom-Json
    if ($timingText -notmatch 'Design Summary\s*:\s*All Constraints Met\.') { throw 'Post-route timing constraints were not met.' }
    if ($ClockHz -ne 27000000) {
        $clockMatches = [regex]::Matches($timingText, '(?m)^\s*clk\|multiplied_clock\.clock_source/pll/CLKOUT0_Inferred\s+([0-9.]+)\s+\{[^}]+\}\s+Generated \(clk\)\s+(\d+)')
        if ($clockMatches.Count -ne 1) { throw 'Missing unique generated CPU clock in the timing report.' }
        $period = [double]::Parse($clockMatches[0].Groups[1].Value,[System.Globalization.CultureInfo]::InvariantCulture)
        if ([math]::Abs($period - 1e9 / $ClockHz) -gt 0.005 -or [int]$clockMatches[0].Groups[2].Value -lt 1) { throw 'Generated CPU clock period or synchronous loads do not match the build.' }
        $manifest['ConstrainedCpuPeriodNs'] = $period
    }
    $manifest['UartProfile'] = $UartProfile
    $manifest['ClockHz'] = $ClockHz
    $manifest['ReferenceClockHz'] = 27000000
    $manifest['ClockSource'] = if ($ClockHz -eq 27000000) { 'direct' } else { 'GTP_GPLL' }
    $manifest['Predictor'] = $Predictor
    $manifest['LoadUseBubble'] = $LoadUseBubble
    $manifest['FastICacheHit'] = $FastICacheHit
    $manifest['FetchOverlap'] = $FetchOverlap
    $manifest['FastDCacheRead'] = $FastDCacheRead
    $manifest['FastDCacheWrite'] = $FastDCacheWrite
    $manifest['EarlyDRequest'] = $EarlyDRequest
    $manifest['BtbIndexBits'] = $BtbIndexBits
    $manifest['DataOverlap'] = $DataOverlap
    $manifest['EnableM'] = $EnableM
    $manifest['SupportedIsa'] = if ($EnableM) { 'rv32im' } else { 'rv32i' }
    $manifest['CacheSetBits'] = $CacheSetBits
    $manifest['ICacheSetBits'] = if ($ICacheSetBits) { $ICacheSetBits } else { $CacheSetBits }
    $manifest['CacheEnabled'] = $CacheEnabled
    $manifest['UartBaud'] = $UartBaud
    $manifest['FirmwareSource'] = $firmwareSource
    $manifest['SelftestExternalInterrupt'] = if ($FirmwareHex) { $null } elseif ($UartProfile -eq 'RemoteLab') { 'UART_RX' } else { 'GPIO_KEY1' }
    $manifest['TimingReport'] = $timingPath
    $manifest['TimingConstraintsMet'] = $true
    $manifest['ResourceSummary'] = $resourceSummary
    $manifest['SourceSnapshot'] = $sourceSnapshot
    $manifest['Placement'] = $placement
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($buildRoot, 'manifest.json')) -Encoding utf8BOM
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'pds-latest.json')) -Encoding utf8BOM
    Write-Output "Bitstream: $bitstream"
    Write-Output "SHA-256: $($manifest.BitstreamSha256)"
} catch {
    Write-Error $_
    exit 1
}
