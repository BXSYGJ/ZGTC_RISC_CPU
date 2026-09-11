[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    foreach ($entry in @('run_tests.ps1', 'run_muldiv_core_tests.ps1', 'run_core_tests.ps1', 'run_cached_tests.ps1', 'run_soc_tests.ps1')) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, $entry))
        if ($LASTEXITCODE -ne 0) { throw "Validation phase failed: $entry" }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -ExternalUart
    if ($LASTEXITCODE -ne 0) { throw 'Remote UART IRQ SoC validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -Uncached
    if ($LASTEXITCODE -ne 0) { throw 'Uncached CPU differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -LoadUseBubble
    if ($LASTEXITCODE -ne 0) { throw 'Registered-load CPU differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -LoadUseBubble -Uncached
    if ($LASTEXITCODE -ne 0) { throw 'Uncached registered-load CPU differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -ExternalUart -CacheEnabled 0
    if ($LASTEXITCODE -ne 0) { throw 'Uncached SoC validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -ExternalUart -Predictor 0 -CacheSetBits 1
    if ($LASTEXITCODE -ne 0) { throw 'Small-cache no-predictor SoC validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -LoadUseBubble 1
    if ($LASTEXITCODE -ne 0) { throw 'Registered-load GPIO IRQ SoC validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -LoadUseBubble 1 -ExternalUart
    if ($LASTEXITCODE -ne 0) { throw 'Registered-load UART IRQ SoC validation failed.' }
    foreach ($bubble in @(0, 1)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastICacheHit -LoadUseBubble:([bool]$bubble)
        if ($LASTEXITCODE -ne 0) { throw 'Early I-cache differential validation failed.' }
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastICacheHit 1 -LoadUseBubble $bubble -ExternalUart
        if ($LASTEXITCODE -ne 0) { throw 'Early I-cache UART IRQ SoC validation failed.' }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastICacheHit 1
    if ($LASTEXITCODE -ne 0) { throw 'Early I-cache GPIO IRQ SoC validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastICacheHit -Uncached
    if ($LASTEXITCODE -ne 0) { throw 'Early I-cache bypass differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_muldiv_core_tests.ps1')) -FetchOverlap 1
    if ($LASTEXITCODE) { throw 'Overlapping fetch M interrupt validation failed.' }
    foreach ($fast in @(0, 1)) {
        foreach ($bubble in @(0, 1)) {
            & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FetchOverlap -FastICacheHit:([bool]$fast) -LoadUseBubble:([bool]$bubble)
            if ($LASTEXITCODE) { throw 'Overlapping fetch differential validation failed.' }
        }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FetchOverlap -FastICacheHit -Uncached
    if ($LASTEXITCODE) { throw 'Overlapping fetch uncached validation failed.' }
    foreach ($bubble in @(0, 1)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FetchOverlap 1 -FastICacheHit 1 -LoadUseBubble $bubble -ExternalUart
        if ($LASTEXITCODE) { throw 'Overlapping fetch UART IRQ validation failed.' }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FetchOverlap 1 -FastICacheHit 1
    if ($LASTEXITCODE) { throw 'Overlapping fetch GPIO IRQ validation failed.' }
    foreach ($fast in @(0, 1)) {
        foreach ($bubble in @(0, 1)) {
            & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastDCacheRead -FetchOverlap -FastICacheHit:([bool]$fast) -LoadUseBubble:([bool]$bubble)
            if ($LASTEXITCODE) { throw 'Early D-cache differential validation failed.' }
        }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastDCacheRead -FastICacheHit -FetchOverlap -Uncached
    if ($LASTEXITCODE) { throw 'Early D-cache bypass validation failed.' }
    foreach ($bubble in @(0, 1)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastDCacheRead 1 -FetchOverlap 1 -FastICacheHit 1 -LoadUseBubble $bubble -ExternalUart
        if ($LASTEXITCODE) { throw 'Early D-cache UART IRQ validation failed.' }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastDCacheRead 1 -FetchOverlap 1 -FastICacheHit 1
    if ($LASTEXITCODE) { throw 'Early D-cache GPIO IRQ validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_core_tests.ps1')) -EarlyDRequest
    if ($LASTEXITCODE) { throw 'Early request randomized differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_muldiv_core_tests.ps1')) -EarlyDRequest 1 -FetchOverlap 1
    if ($LASTEXITCODE) { throw 'Early request M interrupt validation failed.' }
    foreach ($fastData in @(0, 1)) {
        foreach ($bubble in @(0, 1)) {
            & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -EarlyDRequest -FastDCacheRead:([bool]$fastData) -FastICacheHit -FetchOverlap -LoadUseBubble:([bool]$bubble)
            if ($LASTEXITCODE) { throw 'Early request cached differential validation failed.' }
        }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -EarlyDRequest -Uncached
    if ($LASTEXITCODE) { throw 'Early request uncached differential validation failed.' }
    foreach ($bubble in @(0, 1)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -LoadUseBubble $bubble -ExternalUart
        if ($LASTEXITCODE) { throw 'Early request UART IRQ validation failed.' }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1
    if ($LASTEXITCODE) { throw 'Early request GPIO IRQ validation failed.' }
    foreach ($btbBits in @(6, 7)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_core_tests.ps1')) -BtbIndexBits $btbBits -EarlyDRequest
        if ($LASTEXITCODE) { throw 'BTB capacity randomized differential validation failed.' }
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -BtbIndexBits $btbBits -CacheSetBits 6 -EarlyDRequest -FastDCacheRead -FastICacheHit -FetchOverlap -LoadUseBubble
        if ($LASTEXITCODE) { throw 'BTB capacity cached differential validation failed.' }
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_muldiv_core_tests.ps1')) -BtbIndexBits $btbBits -EarlyDRequest 1 -FetchOverlap 1
        if ($LASTEXITCODE) { throw 'BTB capacity precise interrupt validation failed.' }
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -BtbIndexBits $btbBits -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -LoadUseBubble 1 -ExternalUart
        if ($LASTEXITCODE) { throw 'BTB capacity UART IRQ validation failed.' }
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -BtbIndexBits $btbBits -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -LoadUseBubble 1
        if ($LASTEXITCODE) { throw 'BTB capacity GPIO IRQ validation failed.' }
    }
    foreach ($earlyData in @(0, 1)) {
        foreach ($fastData in @(0, 1)) {
            foreach ($bubble in @(0, 1)) {
                & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -DataOverlap -BtbIndexBits 6 -EarlyDRequest:([bool]$earlyData) -FastDCacheRead:([bool]$fastData) -FastICacheHit -FetchOverlap -LoadUseBubble:([bool]$bubble)
                if ($LASTEXITCODE) { throw 'Data-overlap cached differential validation failed.' }
            }
        }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -DataOverlap -BtbIndexBits 7 -CacheSetBits 6 -EarlyDRequest -FastDCacheRead -FastICacheHit -FetchOverlap -LoadUseBubble
    if ($LASTEXITCODE) { throw 'Data-overlap large cache differential validation failed.' }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -DataOverlap -BtbIndexBits 6 -EarlyDRequest -FastICacheHit -FetchOverlap -Uncached
    if ($LASTEXITCODE) { throw 'Data-overlap uncached differential validation failed.' }
    foreach ($bubble in @(0, 1)) {
        & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -DataOverlap 1 -BtbIndexBits 6 -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -LoadUseBubble $bubble -ExternalUart
        if ($LASTEXITCODE) { throw 'Data-overlap UART IRQ validation failed.' }
    }
    & pwsh -NoProfile -File ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -DataOverlap 1 -BtbIndexBits 6 -EarlyDRequest 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -LoadUseBubble 1
    if ($LASTEXITCODE) { throw 'Data-overlap GPIO IRQ validation failed.' }
    $checkerProject = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $checkerLinux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $checkerProject).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL checker path conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_coremark_checker.py"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark checker mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_compare_coremark.py"
    if ($LASTEXITCODE -ne 0) { throw 'Paired CoreMark comparison mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_performance_target.py"
    if ($LASTEXITCODE -ne 0) { throw 'Performance target gate mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_profile_coremark.py"
    if ($LASTEXITCODE -ne 0) { throw 'Retirement profile mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_scope_decode.py"
    if ($LASTEXITCODE -ne 0) { throw 'Scope decoder mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_ila_analyze.py"
    if ($LASTEXITCODE -ne 0) { throw 'ILA analyzer mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_pds_report.py"
    if ($LASTEXITCODE -ne 0) { throw 'PDS report parser mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_package_release.py"
    if ($LASTEXITCODE -ne 0) { throw 'Package integrity mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_boundary_scan_decode.py"
    if ($LASTEXITCODE -ne 0) { throw 'Boundary snapshot decoder mutation tests failed.' }
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $sources = @('rv32_core', 'rv32_machine', 'rv32_decode', 'rv32_alu', 'rv32_btb', 'rv32_muldiv') | ForEach-Object { "$linuxProject/rtl/$_.sv" }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_core @sources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator RTL lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_core -GLOAD_USE_BUBBLE=1 @sources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator registered-load RTL lint failed.' }
    $memorySources = @('rv32_memory_system', 'rv32_cache', 'rv32_uncached', 'rv32_burst_arbiter', 'rv32_burst_ram') | ForEach-Object { "$linuxProject/rtl/$_.sv" }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_memory_system @memorySources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator memory-system lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_memory_system -GENABLE_CACHE=0 @memorySources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator uncached memory-system lint failed.' }
    $socSources = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($project, 'rtl')) -Filter '*.sv' | Sort-Object Name | ForEach-Object { "$linuxProject/rtl/$($_.Name)" })
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator board-level lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GLOAD_USE_BUBBLE=1 @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator registered-load board-level lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GFAST_ICACHE_HIT=1 @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator early I-cache board-level lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GFAST_ICACHE_HIT=1 -GLOAD_USE_BUBBLE=1 @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator early I-cache registered-load board lint failed.' }
    foreach ($bubble in @(0, 1)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GENABLE_M=1 -GFAST_ICACHE_HIT=1 "-GLOAD_USE_BUBBLE=$bubble" @socSources
        if ($LASTEXITCODE -ne 0) { throw 'Verilator M-extension board lint failed.' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 "-GLOAD_USE_BUBBLE=$bubble" @socSources
        if ($LASTEXITCODE) { throw 'Verilator overlapping fetch M board lint failed.' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GFAST_DCACHE_READ=1 -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 "-GLOAD_USE_BUBBLE=$bubble" @socSources
        if ($LASTEXITCODE) { throw 'Verilator early D-cache M board lint failed.' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GEARLY_D_REQUEST=1 -GFAST_DCACHE_READ=1 -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 "-GLOAD_USE_BUBBLE=$bubble" @socSources
        if ($LASTEXITCODE) { throw 'Verilator EX-stage data request M board lint failed.' }
    }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GENABLE_CACHE=0 @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator uncached board-level lint failed.' }
    foreach ($btbBits in @(1, 6, 7, 8)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top "-GBTB_INDEX_BITS=$btbBits" -GCACHE_SET_BITS=6 -GEARLY_D_REQUEST=1 -GFAST_DCACHE_READ=1 -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 -GLOAD_USE_BUBBLE=1 @socSources
        if ($LASTEXITCODE) { throw 'Verilator BTB capacity board lint failed.' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GDATA_OVERLAP=1 "-GBTB_INDEX_BITS=$btbBits" -GCACHE_SET_BITS=6 -GEARLY_D_REQUEST=1 -GFAST_DCACHE_READ=1 -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 -GLOAD_USE_BUBBLE=1 @socSources
        if ($LASTEXITCODE) { throw 'Verilator data-overlap board lint failed.' }
    }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_trace_checker.py" "$linuxProject/build/core_selftest.bin" "$linuxProject/build/core_p1_12345678.trace"
    if ($LASTEXITCODE -ne 0) { throw 'Reference checker mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_memory_overlap_controls.py"
    if ($LASTEXITCODE) { throw 'Memory response-owner mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_mul_request_capture.py"
    if ($LASTEXITCODE) { throw 'Multiply request-capture mutation tests failed.' }
    $carrySaveTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_mul_carry_save.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $carrySaveTest
    if ($LASTEXITCODE) { throw 'Carry-save multiply arithmetic and protocol controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_address_bounds.py"
    if ($LASTEXITCODE) { throw 'Cache address-bound mutation tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_btb_address_bounds.py"
    if ($LASTEXITCODE) { throw 'BTB address-bound mutation tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastDCacheWrite -FastDCacheRead -FastICacheHit -FetchOverlap -EarlyDRequest -DataOverlap -BtbIndexBits 6 -CacheSetBits 1,6
    if ($LASTEXITCODE) { throw 'Fast-write cached CPU differential tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_cached_tests.ps1')) -FastDCacheWrite -FastICacheHit -FetchOverlap -EarlyDRequest -DataOverlap -BtbIndexBits 6 -CacheSetBits 6
    if ($LASTEXITCODE) { throw 'Write-only early-response CPU tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastDCacheWrite 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -EarlyDRequest 1 -DataOverlap 1 -BtbIndexBits 6 -CacheSetBits 6 -ExternalUart
    if ($LASTEXITCODE) { throw 'Fast-write SoC tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_soc_tests.ps1')) -FastDCacheWrite 1 -FastDCacheRead 1 -FastICacheHit 1 -FetchOverlap 1 -EarlyDRequest 1 -DataOverlap 1 -BtbIndexBits 6 -CacheSetBits 6 -CacheEnabled 0
    if ($LASTEXITCODE) { throw 'Fast-write option bypass tests failed.' }
    foreach ($readMode in @(0,1)) {
        foreach ($bubble in @(0,1)) {
            & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GFAST_DCACHE_WRITE=1 "-GFAST_DCACHE_READ=$readMode" "-GLOAD_USE_BUBBLE=$bubble" -GDATA_OVERLAP=1 -GBTB_INDEX_BITS=6 -GCACHE_SET_BITS=6 -GEARLY_D_REQUEST=1 -GFETCH_OVERLAP=1 -GENABLE_M=1 -GFAST_ICACHE_HIT=1 @socSources
            if ($LASTEXITCODE) { throw 'Fast-write board lint failed.' }
        }
    }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_trap_value_controls.py"
    if ($LASTEXITCODE) { throw 'Trap-value source negative controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_fast_write_controls.py"
    if ($LASTEXITCODE) { throw 'Fast-write mutation controls failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_cached_run_contract.ps1'))
    if ($LASTEXITCODE) { throw 'Cached runner argument contract failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_geometry_controls.py"
    if ($LASTEXITCODE) { throw 'Asymmetric geometry negative controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_coremark_compiled_harness.py"
    if ($LASTEXITCODE) { throw 'Compiled driver negative controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_coremark_compiled.py"
    if ($LASTEXITCODE) { throw 'Compiled simulation evidence guards failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_coremark_run_contract.ps1'))
    if ($LASTEXITCODE) { throw 'CoreMark runner contract tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_instruction_cache_contract.ps1'))
    if ($LASTEXITCODE -ne 0) { throw 'Instruction cache parameter contract failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_asymmetric_tests.ps1'))
    if ($LASTEXITCODE) { throw 'Asymmetric cache integration regression failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'run_gpio_tests.ps1'))
    if ($LASTEXITCODE) { throw 'GPIO diagnostic integration failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_gpio_diagnostic.py"
    if ($LASTEXITCODE) { throw 'GPIO diagnostic negative controls failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_ila_run_contract.ps1'))
    if ($LASTEXITCODE) { throw 'ILA target preflight tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_ila_target120.py"
    if ($LASTEXITCODE) { throw 'ILA target analysis tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_ila_run_contract.ps1')) -Profile Target132Carry
    if ($LASTEXITCODE) { throw 'ILA132 carry preflight tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_ila_placement_contract.ps1'))
    if ($LASTEXITCODE) { throw 'ILA placement argument tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_ila_exit_contract.ps1'))
    if ($LASTEXITCODE) { throw 'ILA successful exit contract failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_ila_target132_carry.py"
    if ($LASTEXITCODE) { throw 'ILA132 carry analysis tests failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_ila_run_contract.ps1')) -Profile Target132Kept
    if ($LASTEXITCODE) { throw 'ILA132 kept preflight tests failed.' }
    $keptIlaTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_ila_target132_kept.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $keptIlaTest
    if ($LASTEXITCODE) { throw 'ILA132 kept analysis tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_fast_low_mul.py"
    if ($LASTEXITCODE) { throw 'Fast low multiply handshake controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_forward_data_controls.py"
    if ($LASTEXITCODE) { throw 'Forward data qualification controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_lookup_data.py"
    if ($LASTEXITCODE) { throw 'Cache lookup data controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_frequency_candidate.py"
    if ($LASTEXITCODE) { throw 'Explicit frequency candidate gates failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_mmio_payload.py"
    if ($LASTEXITCODE) { throw 'MMIO payload qualification controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_divider_idle_clear.py"
    if ($LASTEXITCODE) { throw 'Divider idle remainder controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_divider_operand_capture.py"
    if ($LASTEXITCODE) { throw 'Divider operand capture controls failed.' }
    & ([System.IO.Path]::Combine($PSScriptRoot, 'test_pds_placement_contract.ps1'))
    if ($LASTEXITCODE) { throw 'PDS placement configuration tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_address_fanout.py"
    if ($LASTEXITCODE) { throw 'Native cache address fanout audit tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_request_capture.py"
    if ($LASTEXITCODE) { throw 'Cache split request capture tests failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_btb_folded_index.py"
    if ($LASTEXITCODE) { throw 'Folded BTB index controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_divider_zero_payload.py"
    if ($LASTEXITCODE) { throw 'Divider exceptional response payload controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_alu_carry_select.py"
    if ($LASTEXITCODE) { throw 'Carry-select ALU boundary and mutation tests failed.' }
    $onehotAluTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_alu_onehot_output.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $onehotAluTest
    if ($LASTEXITCODE) { throw 'Isolated onehot ALU selection and rejected-variant controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_address_carry_select.py"
    if ($LASTEXITCODE) { throw 'Address carry-select arithmetic and alignment controls failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_cache_ready_payload.py"
    if ($LASTEXITCODE) { throw 'Cache ready payload equivalence and qualification controls failed.' }
    $syncReadTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_cache_synchronous_read.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $syncReadTest
    if ($LASTEXITCODE) { throw 'Synchronous read-only cache equivalence and forwarding controls failed.' }
    foreach ($testName in @('test_branch_history.py', 'test_branch_profile_harness.py', 'test_btb_local_history.py', 'test_btb_history_width.py', 'test_cache_tag_pipeline.py', 'test_cache_synchronous_writable.py', 'test_address_partition.py', 'test_instruction_cache_capacity.py', 'test_instruction_cache_parameters.py')) {
        $historyTest = [System.IO.Path]::Combine($linuxProject, 'scripts', $testName).Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $historyTest
        if ($LASTEXITCODE) { throw "Branch profile or isolated local-history BTB controls failed: $testName" }
    }
    $mmioPayloadTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_mmio_ready_payload.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $mmioPayloadTest
    if ($LASTEXITCODE) { throw 'MMIO payload cycle-equivalence and mutation controls failed.' }
    $fetchPcTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_fetch_pc_precompute.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $fetchPcTest
    if ($LASTEXITCODE) { throw 'Fetch PC precompute boundary, priority and mutation controls failed.' }
    $lruStorageTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_cache_lru_storage.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $lruStorageTest
    if ($LASTEXITCODE) { throw 'Reset-free LRU semantics, reset and mutation controls failed.' }
    $collisionForwardTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_cache_collision_forward.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $collisionForwardTest
    if ($LASTEXITCODE) { throw 'Cache collision equivalence, forwarding/writeback coverage and mutation controls failed.' }
    $forwardParallelTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_forward_parallel.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $forwardParallelTest
    if ($LASTEXITCODE) { throw 'Parallel forwarding priority, load-format and poisoned-response controls failed.' }
    $loadUseProfileTest = [System.IO.Path]::Combine($linuxProject, 'scripts', 'test_load_use_profile.py').Replace([System.IO.Path]::DirectorySeparatorChar, [char]47)
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $loadUseProfileTest
    if ($LASTEXITCODE) { throw 'Retirement trace parsing and dependency accounting controls failed.' }
    Write-Output 'PASS validation: units, CPU, reference, memory comparison, lint, checker mutation tests.'
} catch {
    Write-Error $_
    exit 1
}
