param([ValidateRange(0,10)][int]$ICacheSetBits = 0, [ValidateRange(1,10)][int]$Iterations = 1, [switch]$LinkerRelaxation, [switch]$LinkTimeOptimization, [ValidateRange(0,1)][int]$DataOverlap = 0, [ValidateRange(1,8)][int]$BtbIndexBits = 4, [ValidateRange(0,1)][int]$EarlyDRequest = 0, [switch]$UnrollLoops, [ValidateRange(0,1)][int]$FastDCacheWrite = 0, [ValidateRange(0,1)][int]$FastDCacheRead = 0, [ValidateRange(0,1)][int]$FetchOverlap = 0, [switch]$Profile, [ValidateRange(0,1)][int]$EnableM = 0, [ValidateSet('O2','O3','Os')][string]$Optimization = 'O2', [ValidateRange(0,1)][int]$FastICacheHit = 0, [ValidateRange(0,1)][int]$LoadUseBubble = 0, [switch]$ValidationRun, [ValidateRange(0,4000)][int]$ConsoleDelayCycles = 0, [ValidateRange(0,1)][int]$Predictor = 1, [ValidateRange(1,8)][int]$CacheSetBits = 4, [ValidateRange(0,1)][int]$CacheEnabled = 1, [ValidateSet(27000000,54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,120000000,126000000,132000000,135000000,162000000,180000000,194400000,216000000,270000000)][int]$ClockHz = 27000000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_coremark.ps1')) -LinkerRelaxation:$LinkerRelaxation -LinkTimeOptimization:$LinkTimeOptimization -UnrollLoops:$UnrollLoops -EnableM $EnableM -Optimization $Optimization -Iterations $Iterations -ValidationRun:$ValidationRun -ConsoleDelayCycles $ConsoleDelayCycles -ClockHz $ClockHz
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $manifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','coremark-latest.json')) -Raw | ConvertFrom-Json
    if ($manifest.Iterations -ne $Iterations -or $manifest.ClockHz -ne $ClockHz -or $manifest.ConsoleDelayCycles -ne $ConsoleDelayCycles -or $manifest.ValidationRun -ne [bool]$ValidationRun -or $manifest.EnableM -ne $EnableM -or $manifest.Optimization -ne $Optimization -or $manifest.UnrollLoops -ne [bool]$UnrollLoops -or $manifest.LinkTimeOptimization -ne [bool]$LinkTimeOptimization -or $manifest.LinkerRelaxation -ne [bool]$LinkerRelaxation) {
        throw 'CoreMark build manifest does not match the requested run; possible concurrent build.'
    }
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $sources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project,'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linuxProject/rtl/$($_.Name)" }) + @("$linuxProject/sim/coremark_tb.sv")
    $runName = $manifest.RunName
    $firmwareName = $runName
    $profileArguments = @()
    $runName += "_bp${Predictor}_cs${CacheSetBits}_cache$CacheEnabled"
    if ($ICacheSetBits) { $runName += "_ics$ICacheSetBits" }
    if ($BtbIndexBits -ne 4) { $runName += "_btb$BtbIndexBits" }
    if ($DataOverlap) { $runName += '_dataoverlap' }
    if ($LoadUseBubble) { $runName += '_loadbubble' }
    if ($FastICacheHit) { $runName += '_fastihit' }
    if ($FetchOverlap) { $runName += '_fetchoverlap' }
            if ($FastDCacheRead) { $runName += '_fastdread' }
            if ($FastDCacheWrite) { $runName += '_fastdwrite' }
            if ($EarlyDRequest) { $runName += '_earlydreq' }
    if ($Profile) {
        . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
        $profileToolchain = Get-RiscvToolchain
        $runName += '_profile_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0,8))
        $symbols = & wsl.exe --distribution Ubuntu-22.04 --exec $profileToolchain.Nm -S --defined-only "$linuxProject/build/$firmwareName.elf"
        if ($LASTEXITCODE) { throw 'Profile symbol extraction failed.' }
        $symbols | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"$runName.symbols")) -Encoding utf8BOM
        $boundaries = @{}
        foreach ($line in $symbols) {
            if ($line -match '^([0-9a-f]{8}) [0-9a-f]+ T (iterate|stop_time)$') { $boundaries[$Matches[2]] = $Matches[1] }
        }
        if ($boundaries.Count -ne 2) { throw 'Profile requires unique iterate/stop_time symbols.' }
        Copy-Item -LiteralPath ([System.IO.Path]::Combine($project,'build',"$firmwareName.elf")) -Destination ([System.IO.Path]::Combine($project,'build',"$runName.elf"))
        $profileArguments = @("+profile=$linuxProject/build/$runName.hist", "+profile_start=$($boundaries['iterate'])", "+profile_stop=$($boundaries['stop_time'])")
    }
    if (($LinkTimeOptimization -or $LinkerRelaxation) -and -not $Profile) {
        $runName += '_run_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([guid]::NewGuid().ToString('N').Substring(0,8))
    }
    $firmwareSource = [System.IO.Path]::Combine($project,'build',"$firmwareName.hex")
    $firmwareSnapshot = [System.IO.Path]::Combine($project,'build',"$runName.hex")
    Copy-Item -LiteralPath $firmwareSource -Destination $firmwareSnapshot -Force
    if ((Get-FileHash -LiteralPath $firmwareSnapshot -Algorithm SHA256).Hash -ne $manifest.HexSha256) { throw 'CoreMark firmware changed after build; refusing mismatched snapshot.' }
    $runManifest = [ordered]@{ RunName=$runName; FirmwareSha256=(Get-FileHash -LiteralPath $firmwareSnapshot -Algorithm SHA256).Hash; CacheEnabled=$CacheEnabled; Predictor=$Predictor; CacheSetBits=$CacheSetBits; StartedUtc=[datetime]::UtcNow.ToString('o') }
    $runManifest['ICacheSetBits'] = if ($ICacheSetBits) { $ICacheSetBits } else { $CacheSetBits }
    $runManifest['Iterations'] = $Iterations
    $runManifest['FirmwareClockHz'] = $ClockHz
    $runManifest['LoadUseBubble'] = $LoadUseBubble
    $runManifest['FastICacheHit'] = $FastICacheHit
    $runManifest['FetchOverlap'] = $FetchOverlap
    $runManifest['FastDCacheRead'] = $FastDCacheRead
    $runManifest['FastDCacheWrite'] = $FastDCacheWrite
    $runManifest['EarlyDRequest'] = $EarlyDRequest
    $runManifest['DataOverlap'] = $DataOverlap
    $runManifest['BtbIndexBits'] = $BtbIndexBits
    $runManifest['Optimization'] = $Optimization
    $runManifest['UnrollLoops'] = [bool]$UnrollLoops
    $runManifest['LinkTimeOptimization'] = [bool]$LinkTimeOptimization
    $runManifest['LinkerRelaxation'] = [bool]$LinkerRelaxation
    $runManifest['ConsoleDelayCycles'] = $ConsoleDelayCycles
    $runManifest['EnableM'] = $EnableM
    $runManifest['Isa'] = $manifest.Isa
    $runManifest['SimulationClockHz'] = 100000000
    $runManifest['UartModelClockHz'] = 3200
    $runManifest | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"$runName.run.json")) -Encoding utf8BOM
    Write-Output "CoreMark run manifest: $runName.run.json"
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s coremark_tb "-Pcoremark_tb.ICACHE_SET_BITS=$ICacheSetBits" "-Pcoremark_tb.DATA_OVERLAP=$DataOverlap" "-Pcoremark_tb.BTB_INDEX_BITS=$BtbIndexBits" "-Pcoremark_tb.EARLY_D_REQUEST=$EarlyDRequest" "-Pcoremark_tb.FAST_DCACHE_WRITE=$FastDCacheWrite" "-Pcoremark_tb.FAST_DCACHE_READ=$FastDCacheRead" "-Pcoremark_tb.FETCH_OVERLAP=$FetchOverlap" "-Pcoremark_tb.ENABLE_M=$EnableM" "-Pcoremark_tb.ENABLE_PREDICTOR=$Predictor" "-Pcoremark_tb.CACHE_SET_BITS=$CacheSetBits" "-Pcoremark_tb.ENABLE_CACHE=$CacheEnabled" "-Pcoremark_tb.LOAD_USE_BUBBLE=$LoadUseBubble" "-Pcoremark_tb.FAST_ICACHE_HIT=$FastICacheHit" -o "$linuxProject/build/$runName.vvp" @sources
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark simulation compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/$runName.vvp" "+firmware=$linuxProject/build/$runName.hex" "+uart=$linuxProject/build/$runName.uart" @profileArguments
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark simulation failed.' }
    $btbEncoding = if ($BtbIndexBits -eq 4) { 0 } else { $BtbIndexBits }
    $instructionEncoding = if ($ICacheSetBits -and $ICacheSetBits -ne $CacheSetBits) { $ICacheSetBits } else { 0 }
    $configuration = (0x0e020000 -bor ($instructionEncoding -shl 12) -bor (($FastDCacheWrite -band $CacheEnabled) -shl 19) -bor ($DataOverlap -shl 18) -bor ($btbEncoding -shl 20) -bor ($CacheSetBits -shl 8) -bor $Predictor -bor ((1 - $CacheEnabled) -shl 1) -bor ($LoadUseBubble -shl 2) -bor (($FastICacheHit -band $CacheEnabled) -shl 3) -bor ($EnableM -shl 4) -bor ($FetchOverlap -shl 5) -bor (($FastDCacheRead -band $CacheEnabled) -shl 6) -bor ($EarlyDRequest -shl 7)).ToString('x8')
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/check_coremark.py" "$linuxProject/build/$runName.uart" --allow-short --clock-hz $ClockHz --expected-config $configuration --json "$linuxProject/build/$runName.result.json"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark short-run CRC or metadata check failed.' }
    if ($Profile) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/profile_coremark.py" --histogram "$linuxProject/build/$runName.hist" --symbols "$linuxProject/build/$runName.symbols" --firmware "$linuxProject/build/$runName.hex" --elf "$linuxProject/build/$runName.elf" --json "$linuxProject/build/$runName.profile.json"
        if ($LASTEXITCODE) { throw 'Profile conservation/symbol analysis failed.' }
    }
    Write-Output 'PASS CoreMark short-run CRC; duration is not valid for scoring.'
} catch {
    Write-Error $_
    exit 1
}
