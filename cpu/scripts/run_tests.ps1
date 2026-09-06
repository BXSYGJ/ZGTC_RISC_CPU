[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $output = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $output -Force)
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $tests = @(
        @{ Name = 'cache_geometry'; Sources = @('rtl/rv32_alu.sv', 'rtl/rv32_btb.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_core.sv', 'rtl/rv32_decode.sv', 'rtl/rv32_fifo.sv', 'rtl/rv32_machine.sv', 'rtl/rv32_memory_system.sv', 'rtl/rv32_muldiv.sv', 'rtl/rv32_peripherals.sv', 'rtl/rv32_soc.sv', 'rtl/rv32_uart.sv', 'rtl/rv32_uncached.sv', 'sim/cache_geometry_tb.sv') },
        @{ Name = 'trap_value'; Sources = @('rtl/rv32_core.sv', 'rtl/rv32_decode.sv', 'rtl/rv32_alu.sv', 'rtl/rv32_btb.sv', 'rtl/rv32_machine.sv', 'rtl/rv32_muldiv.sv', 'sim/trap_value_tb.sv') },
        @{ Name = 'muldiv'; Sources = @('rtl/rv32_muldiv.sv', 'sim/muldiv_tb.sv') },
        @{ Name = 'decode_alu'; Sources = @('rtl/rv32_decode.sv', 'rtl/rv32_alu.sv', 'sim/decode_alu_tb.sv') },
        @{ Name = 'btb'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv') },
        @{ Name = 'btb16'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb16_tb.sv') },
        @{ Name = 'btb64'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb64_tb.sv') },
        @{ Name = 'btb128'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb128_tb.sv') },
        @{ Name = 'btb256'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb256_tb.sv') },
        @{ Name = 'btb_bounded64'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb_bounded64_tb.sv') },
        @{ Name = 'btb_bounded128'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb_bounded128_tb.sv') },
        @{ Name = 'btb_bounded256'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv', 'sim/btb_bounded256_tb.sv') },
        @{ Name = 'btb_bounds'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_bounds_tb.sv') },
        @{ Name = 'machine'; Sources = @('rtl/rv32_machine.sv', 'sim/machine_tb.sv') },
        @{ Name = 'machine_m'; Sources = @('rtl/rv32_machine.sv', 'sim/machine_tb.sv', 'sim/machine_m_tb.sv') },
        @{ Name = 'cache'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv') },
        @{ Name = 'cache_ro'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_ro_tb.sv') },
        @{ Name = 'cache_ro_fast'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_ro_fast_tb.sv') },
        @{ Name = 'cache_rw_fast'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_rw_fast_tb.sv') },
        @{ Name = 'cache_rw_overlap'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_rw_overlap_tb.sv') },
        @{ Name = 'cache_ro_overlap'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_ro_overlap_tb.sv') },
        @{ Name = 'cache_bounded_rw'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_bounded_rw_tb.sv') },
        @{ Name = 'cache_write_fast'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_write_fast_tb.sv') },
        @{ Name = 'cache_write_overlap'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_write_overlap_tb.sv') },
        @{ Name = 'cache_write_readonly'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_write_readonly_tb.sv') },
        @{ Name = 'cache_bounded_ro'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_bounded_ro_tb.sv') },
        @{ Name = 'cache_bounds'; Sources = @('rtl/rv32_cache.sv', 'rtl/rv32_burst_ram.sv', 'sim/cache_bounds_tb.sv') },
        @{ Name = 'cache_bounds_registered'; Sources = @('rtl/rv32_cache.sv', 'rtl/rv32_burst_ram.sv', 'sim/cache_bounds_tb.sv', 'sim/cache_bounds_registered_tb.sv') },
        @{ Name = 'cache_bounds_large'; Sources = @('rtl/rv32_cache.sv', 'rtl/rv32_burst_ram.sv', 'sim/cache_bounds_tb.sv', 'sim/cache_bounds_large_tb.sv') },
        @{ Name = 'cache_bounds_ro'; Sources = @('rtl/rv32_cache.sv', 'rtl/rv32_burst_ram.sv', 'sim/cache_bounds_tb.sv', 'sim/cache_bounds_ro_tb.sv') },
        @{ Name = 'uncached'; Sources = @('rtl/rv32_uncached.sv', 'sim/uncached_tb.sv') },
        @{ Name = 'uncached_ro'; Sources = @('rtl/rv32_uncached.sv', 'sim/uncached_tb.sv', 'sim/uncached_ro_tb.sv') },
        @{ Name = 'memory_overlap'; Sources = @('rtl/rv32_memory_system.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_uncached.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'sim/memory_overlap_tb.sv') },
        @{ Name = 'memory_overlap_registered'; Sources = @('rtl/rv32_memory_system.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_uncached.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'sim/memory_overlap_tb.sv', 'sim/memory_overlap_registered_tb.sv') },
        @{ Name = 'memory_overlap_stalled'; Sources = @('rtl/rv32_memory_system.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_uncached.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'sim/memory_overlap_tb.sv', 'sim/memory_overlap_stalled_tb.sv') },
        @{ Name = 'memory_overlap_write'; Sources = @('rtl/rv32_memory_system.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_uncached.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'sim/memory_overlap_tb.sv', 'sim/memory_overlap_write_tb.sv') },
        @{ Name = 'memory_asymmetric'; Sources = @('rtl/rv32_memory_system.sv', 'rtl/rv32_cache.sv', 'rtl/rv32_uncached.sv', 'rtl/rv32_burst_arbiter.sv', 'rtl/rv32_burst_ram.sv', 'sim/memory_overlap_tb.sv', 'sim/memory_asymmetric_tb.sv') },
        @{ Name = 'burst'; Sources = @('rtl/rv32_burst_ram.sv', 'rtl/rv32_burst_arbiter.sv', 'sim/burst_tb.sv') },
        @{ Name = 'fifo'; Sources = @('rtl/rv32_fifo.sv', 'sim/fifo_tb.sv') },
        @{ Name = 'uart'; Sources = @('rtl/rv32_uart.sv', 'sim/uart_tb.sv') },
        @{ Name = 'peripherals'; Sources = @('rtl/rv32_peripherals.sv', 'rtl/rv32_uart.sv', 'rtl/rv32_fifo.sv', 'sim/peripherals_tb.sv') }
    )
    $allOutput = [System.Collections.Generic.List[string]]::new()
    foreach ($test in $tests) {
        $sources = $test.Sources | ForEach-Object { "$linuxProject/$_" }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s "$($test.Name)_tb" -o "$linuxProject/build/$($test.Name).vvp" @sources
        if ($LASTEXITCODE -ne 0) { throw "Icarus compilation failed: $($test.Name)" }
        $testOutput = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linuxProject/build/$($test.Name).vvp"
        $testExitCode = $LASTEXITCODE
        $testOutput | ForEach-Object { $allOutput.Add([string]$_); Write-Output $_ }
        $allOutput | Set-Content -LiteralPath ([System.IO.Path]::Combine($output, 'unit-tests.log')) -Encoding utf8BOM
        if ($testExitCode -ne 0 -or -not ($testOutput -match "^PASS $($test.Name) checks=")) { throw "RTL self-test failed or PASS marker missing: $($test.Name)" }
    }
} catch {
    Write-Error $_
    exit 1
}
