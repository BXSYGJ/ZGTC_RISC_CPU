param([ValidateRange(1,10)][int]$InstructionBits = 8)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project=[IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..'))
    $linuxProject=(& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE) { throw 'WSL path conversion failed.' }
    $sources=@(Get-ChildItem -LiteralPath ([IO.Path]::Combine($project,'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linuxProject/rtl/$($_.Name)" })
    & ([IO.Path]::Combine($PSScriptRoot,'test_cached_run_contract.ps1'))
    if ($LASTEXITCODE) { throw 'Cached argument contract failed.' }
    $geometries=@(@{InstructionBits=$InstructionBits;DataBits=6},@{InstructionBits=$InstructionBits;DataBits=7},@{InstructionBits=1;DataBits=3})
    foreach ($geometry in $geometries) {
        & ([IO.Path]::Combine($PSScriptRoot,'run_cached_tests.ps1')) -ICacheSetBits $geometry.InstructionBits -CacheSetBits $geometry.DataBits -BtbIndexBits 8 -FastDCacheWrite -FastDCacheRead -FastICacheHit -FetchOverlap -EarlyDRequest -DataOverlap
        if ($LASTEXITCODE) { throw 'Asymmetric cached differential tests failed.' }
        & ([IO.Path]::Combine($PSScriptRoot,'run_soc_tests.ps1')) -ICacheSetBits $geometry.InstructionBits -CacheSetBits $geometry.DataBits -BtbIndexBits 8 -FastDCacheWrite 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -EarlyDRequest 1 -DataOverlap 1 -ExternalUart
        if ($LASTEXITCODE) { throw 'Asymmetric SoC tests failed.' }
        foreach ($bubble in @(0,1)) {
            & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top "-GICACHE_SET_BITS=$($geometry.InstructionBits)" "-GCACHE_SET_BITS=$($geometry.DataBits)" -GFAST_DCACHE_WRITE=1 -GFAST_DCACHE_READ=1 -GFAST_ICACHE_HIT=1 -GFETCH_OVERLAP=1 -GEARLY_D_REQUEST=1 -GDATA_OVERLAP=1 -GENABLE_M=1 -GBTB_INDEX_BITS=8 "-GLOAD_USE_BUBBLE=$bubble" @sources
            if ($LASTEXITCODE) { throw 'Asymmetric strict board lint failed.' }
        }
    }
    foreach ($readMode in @($false,$true)) {
        & ([IO.Path]::Combine($PSScriptRoot,'run_cached_tests.ps1')) -ICacheSetBits $InstructionBits -CacheSetBits 6 -BtbIndexBits 8 -FastDCacheRead:$readMode -FastDCacheWrite:(-not $readMode) -FastICacheHit -FetchOverlap -EarlyDRequest -DataOverlap
        if ($LASTEXITCODE) { throw 'Independent early read/write CPU tests failed.' }
    }
    & ([IO.Path]::Combine($PSScriptRoot,'run_cached_tests.ps1')) -ICacheSetBits $InstructionBits -CacheSetBits 6 -BtbIndexBits 8 -Uncached -FastDCacheWrite -FastDCacheRead -FastICacheHit -FetchOverlap -EarlyDRequest -DataOverlap
    if ($LASTEXITCODE) { throw 'Asymmetric bypass CPU tests failed.' }
    & ([IO.Path]::Combine($PSScriptRoot,'run_soc_tests.ps1')) -ICacheSetBits $InstructionBits -CacheSetBits 6 -CacheEnabled 0 -BtbIndexBits 8 -FastDCacheWrite 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -EarlyDRequest 1 -DataOverlap 1
    if ($LASTEXITCODE) { throw 'Asymmetric bypass SoC tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top "-GICACHE_SET_BITS=$InstructionBits" -GCACHE_SET_BITS=6 -GENABLE_CACHE=0 @sources
    if ($LASTEXITCODE) { throw 'Asymmetric bypass lint failed.' }
    Write-Output "PASS asymmetric cache integration: geometry, reference, SoC, bypass, independent read/write modes, lint."
} catch {
    Write-Error $_
    exit 1
}
