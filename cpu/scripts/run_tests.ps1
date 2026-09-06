[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $output = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $output -Force)
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $tests = @(
        @{ Name = 'decode_alu'; Sources = @('rtl/rv32_decode.sv', 'rtl/rv32_alu.sv', 'sim/decode_alu_tb.sv') },
        @{ Name = 'btb'; Sources = @('rtl/rv32_btb.sv', 'sim/btb_tb.sv') },
        @{ Name = 'machine'; Sources = @('rtl/rv32_machine.sv', 'sim/machine_tb.sv') },
        @{ Name = 'cache'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv') },
        @{ Name = 'cache_ro'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_ro_tb.sv') },
        @{ Name = 'cache_ro_fast'; Sources = @('rtl/rv32_cache.sv', 'sim/cache_tb.sv', 'sim/cache_ro_fast_tb.sv') },
        @{ Name = 'uncached'; Sources = @('rtl/rv32_uncached.sv', 'sim/uncached_tb.sv') },
        @{ Name = 'uncached_ro'; Sources = @('rtl/rv32_uncached.sv', 'sim/uncached_tb.sv', 'sim/uncached_ro_tb.sv') },
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
