[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    foreach ($entry in @('run_tests.ps1', 'run_core_tests.ps1', 'run_cached_tests.ps1', 'run_soc_tests.ps1')) {
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
    $checkerProject = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $checkerLinux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $checkerProject).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL checker path conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$checkerLinux/scripts/test_coremark_checker.py"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark checker mutation tests failed.' }
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
    $sources = @('rv32_core', 'rv32_machine', 'rv32_decode', 'rv32_alu', 'rv32_btb') | ForEach-Object { "$linuxProject/rtl/$_.sv" }
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
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --lint-only --Wall --top-module rv32_board_top -GENABLE_CACHE=0 @socSources
    if ($LASTEXITCODE -ne 0) { throw 'Verilator uncached board-level lint failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/test_trace_checker.py" "$linuxProject/build/core_selftest.bin" "$linuxProject/build/core_p1_12345678.trace"
    if ($LASTEXITCODE -ne 0) { throw 'Reference checker mutation tests failed.' }
    Write-Output 'PASS validation: units, CPU, reference, memory comparison, lint, checker mutation tests.'
} catch {
    Write-Error $_
    exit 1
}
