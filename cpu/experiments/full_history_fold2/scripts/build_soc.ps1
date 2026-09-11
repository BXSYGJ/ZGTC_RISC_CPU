param([switch]$ExternalUart)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    [void](New-Item -ItemType Directory -Path ([System.IO.Path]::Combine($project, 'build')) -Force)
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $uartIrq = if ($ExternalUart) { 1 } else { 0 }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc -march=rv32i -mabi=ilp32 -msmall-data-limit=0 "-DEXTERNAL_UART=$uartIrq" -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles '-Wl,--no-relax' -T "$linuxProject/sw/link_soc.ld" -o "$linuxProject/build/soc_selftest.elf" "$linuxProject/sw/start.S" "$linuxProject/sw/soc_selftest.c" -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'C firmware compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linuxProject/build/soc_selftest.elf" "$linuxProject/build/soc_selftest.bin"
    if ($LASTEXITCODE -ne 0) { throw 'Binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/bin_to_hex.py" "$linuxProject/build/soc_selftest.bin" "$linuxProject/build/soc_selftest.hex" --bytes 65536
    if ($LASTEXITCODE -ne 0) { throw 'Memory image conversion failed.' }
    $header = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Readelf -h "$linuxProject/build/soc_selftest.elf"
    if ($LASTEXITCODE -ne 0 -or -not ($header -match 'Class:\s+ELF32') -or -not ($header -match 'Machine:\s+RISC-V')) { throw 'Firmware is not ELF32 RISC-V.' }
    $disassembly = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objdump -d "$linuxProject/build/soc_selftest.elf"
    if ($LASTEXITCODE -ne 0) { throw 'Disassembly failed.' }
    $disassembly | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'soc_selftest.dis')) -Encoding utf8BOM
} catch {
    Write-Error $_
    exit 1
}
