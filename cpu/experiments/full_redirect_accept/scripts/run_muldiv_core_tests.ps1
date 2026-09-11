param([ValidateRange(1,8)][int]$BtbIndexBits = 4, [ValidateRange(0,1)][int]$EarlyDRequest = 0, [ValidateRange(0,1)][int]$FetchOverlap = 0)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $linux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE) { throw 'Project conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc -march=rv32im -mabi=ilp32 -nostdlib -nostartfiles '-Wl,--no-relax' -T "$linux/sim/isa/link.ld" -o "$linux/build/muldiv_interrupt.elf" "$linux/sw/muldiv_interrupt.S"
    if ($LASTEXITCODE) { throw 'Interrupt firmware compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linux/build/muldiv_interrupt.elf" "$linux/build/muldiv_interrupt.bin"
    if ($LASTEXITCODE) { throw 'Interrupt binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linux/scripts/bin_to_hex.py" "$linux/build/muldiv_interrupt.bin" "$linux/build/muldiv_interrupt.hex" --bytes 65536
    if ($LASTEXITCODE) { throw 'Interrupt image conversion failed.' }
    $symbols = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Nm -n "$linux/build/muldiv_interrupt.elf"
    if ($LASTEXITCODE) { throw 'Interrupt symbol extraction failed.' }
    $addresses = @{}
    foreach ($line in $symbols) { if ($line -match '^([0-9a-f]{8}) T (target_div|target_mul|target_mulh)$') { $addresses[$Matches[2]]=$Matches[1] } }
    if ($addresses.Count -ne 3) { throw 'Required interrupt target symbols missing.' }
    $sources = @('rv32_core','rv32_decode','rv32_machine','rv32_alu','rv32_btb','rv32_muldiv') | ForEach-Object { "$linux/rtl/$_.sv" }
    $records = [System.Collections.Generic.List[string]]::new()
    foreach ($bubble in @(0,1)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -Wall -s muldiv_core_tb "-Pmuldiv_core_tb.BTB_INDEX_BITS=$BtbIndexBits" "-Pmuldiv_core_tb.EARLY_D_REQUEST=$EarlyDRequest" "-Pmuldiv_core_tb.FETCH_OVERLAP=$FetchOverlap" "-Pmuldiv_core_tb.LOAD_USE_BUBBLE=$bubble" -o "$linux/build/muldiv_core_${bubble}_overlap${FetchOverlap}_early${EarlyDRequest}_btb$BtbIndexBits.vvp" @sources "$linux/sim/muldiv_core_tb.sv"
        if ($LASTEXITCODE) { throw 'Interrupt simulator compilation failed.' }
        foreach ($target in @('target_div','target_mul','target_mulh')) {
            $delays = if ($target -eq 'target_div') { @(0,1,15,30) } elseif ($target -eq 'target_mulh') { @(0,1) } else { @(0) }
            foreach ($delay in $delays) {
                $output = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp "$linux/build/muldiv_core_${bubble}_overlap${FetchOverlap}_early${EarlyDRequest}_btb$BtbIndexBits.vvp" "+firmware=$linux/build/muldiv_interrupt.hex" "+irq_pc=$($addresses[$target])" "+irq_delay=$delay"
                if ($LASTEXITCODE -or ($output -join "`n") -notmatch "PASS muldiv_core checks=2 irq_pc=$($addresses[$target]) delay=$delay loadbubble=$bubble") { throw 'Precise interrupt/cancellation test failed.' }
                foreach ($line in $output) { $records.Add($line); Write-Output $line }
            }
        }
    }
    $records | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"muldiv-interrupt-overlap${FetchOverlap}-early${EarlyDRequest}-btb$BtbIndexBits-tests.log")) -Encoding utf8BOM
} catch {
    Write-Error $_
    exit 1
}
