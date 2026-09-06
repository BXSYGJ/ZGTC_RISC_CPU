param([ValidateRange(0,8)][int]$ICacheSetBits = 0, [switch]$DataOverlap, [ValidateRange(1,8)][int]$BtbIndexBits = 4, [ValidateRange(1,8)][int[]]$CacheSetBits = @(1,4), [switch]$EarlyDRequest, [switch]$FastDCacheWrite, [switch]$FastDCacheRead, [switch]$FetchOverlap, [switch]$FastICacheHit, [switch]$Uncached, [switch]$LoadUseBubble)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($PSScriptRoot, 'build_selftest.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $modules = @('rv32_core', 'rv32_machine', 'rv32_decode', 'rv32_alu', 'rv32_btb', 'rv32_muldiv', 'rv32_cache', 'rv32_uncached', 'rv32_memory_system', 'rv32_burst_ram', 'rv32_burst_arbiter')
    $sources = @($modules | ForEach-Object { "$linuxProject/rtl/$_.sv" }) + @("$linuxProject/sim/cached_core_tb.sv")
    $allOutput = [System.Collections.Generic.List[string]]::new()
    $enableCache = if ($Uncached) { 0 } else { 1 }
    $loadBubble = if ($LoadUseBubble) { 1 } else { 0 }
    $fastHit = if ($FastICacheHit) { 1 } else { 0 }
    $overlap = if ($FetchOverlap) { 1 } else { 0 }
    $fastData = if ($FastDCacheRead) { 1 } else { 0 }
    $fastWrite = if ($FastDCacheWrite) { 1 } else { 0 }

    $overlapData = if ($DataOverlap) { 1 } else { 0 }
    $earlyData = if ($EarlyDRequest) { 1 } else { 0 }
    $setConfigurations = if ($PSBoundParameters.ContainsKey('CacheSetBits')) { @($CacheSetBits) } elseif ($Uncached) { @(4) } else { @(1, 4) }
    $logName = if ($Uncached) { 'uncached-core-tests.log' } else { 'cached-tests.log' }
    if ($LoadUseBubble) { $logName = if ($Uncached) { 'uncached-load-bubble-tests.log' } else { 'cached-load-bubble-tests.log' } }
    if ($FastICacheHit) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-fastihit.log' }
    if ($FetchOverlap) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-fetchoverlap.log' }
    if ($FastDCacheRead) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-fastdread.log' }
    if ($FastDCacheWrite) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-fastdwrite.log' }
    if ($EarlyDRequest) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-earlydreq.log' }
    if ($PSBoundParameters.ContainsKey('CacheSetBits')) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-sets' + ($CacheSetBits -join '-') + '.log' }
    if ($BtbIndexBits -ne 4) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + "-btb$BtbIndexBits.log" }
    if ($DataOverlap) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + '-dataoverlap.log' }
    if ($ICacheSetBits) { $logName = [System.IO.Path]::GetFileNameWithoutExtension($logName) + "-ics$ICacheSetBits.log" }
    foreach ($sets in $setConfigurations) {
        foreach ($predictor in @(0, 1)) {
            $runName = "cached_s${sets}_p$predictor"
            if ($ICacheSetBits) { $runName += "_ics$ICacheSetBits" }
            if ($DataOverlap) { $runName += '_dataoverlap' }
            if ($BtbIndexBits -ne 4) { $runName += "_btb$BtbIndexBits" }
            if ($Uncached) { $runName += '_nocache' }
            if ($LoadUseBubble) { $runName += '_loadbubble' }
        if ($FastICacheHit) { $runName += '_fastihit' }
            if ($FetchOverlap) { $runName += '_fetchoverlap' }
            if ($FastDCacheRead) { $runName += '_fastdread' }
            if ($FastDCacheWrite) { $runName += '_fastdwrite' }
            if ($EarlyDRequest) { $runName += '_earlydreq' }
            & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s cached_core_tb "-Pcached_core_tb.ICACHE_SET_BITS=$ICacheSetBits" "-Pcached_core_tb.DATA_OVERLAP=$overlapData" "-Pcached_core_tb.BTB_INDEX_BITS=$BtbIndexBits" "-Pcached_core_tb.EARLY_D_REQUEST=$earlyData" "-Pcached_core_tb.FAST_DCACHE_WRITE=$fastWrite" "-Pcached_core_tb.FAST_DCACHE_READ=$fastData" "-Pcached_core_tb.FETCH_OVERLAP=$overlap" "-Pcached_core_tb.CACHE_SETS=$sets" "-Pcached_core_tb.PREDICTOR=$predictor" "-Pcached_core_tb.ENABLE_CACHE=$enableCache" "-Pcached_core_tb.LOAD_USE_BUBBLE=$loadBubble" "-Pcached_core_tb.FAST_ICACHE_HIT=$fastHit" -o "$linuxProject/build/$runName.vvp" @sources
            if ($LASTEXITCODE -ne 0) { throw 'Cached CPU compilation failed.' }
            $testOutput = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/$runName.vvp" "+firmware=$linuxProject/build/core_selftest.hex" "+trace=$linuxProject/build/$runName.trace" "+memory_out=$linuxProject/build/$runName.memory"
            $testExitCode = $LASTEXITCODE
            $testOutput | ForEach-Object { $allOutput.Add("${runName}: $_"); Write-Output $_ }
            $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', $logName)) -Encoding utf8BOM
            if ($testExitCode -ne 0 -or -not ($testOutput -match '^PASS cached_core checks=')) { throw "Cached CPU test failed: $runName" }
            $referenceOutput = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/check_trace.py" "$linuxProject/build/core_selftest.bin" "$linuxProject/build/$runName.trace" --memory "$linuxProject/build/$runName.memory"
            if ($LASTEXITCODE -ne 0) { throw "Cached CPU reference comparison failed: $runName" }
            $referenceOutput | ForEach-Object { $allOutput.Add([string]$_); Write-Output $_ }
            $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', $logName)) -Encoding utf8BOM
        }
    }
} catch {
    Write-Error $_
    exit 1
}
