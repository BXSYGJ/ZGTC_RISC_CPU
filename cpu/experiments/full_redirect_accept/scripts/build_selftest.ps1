[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    [void](New-Item -ItemType Directory -Path ([System.IO.Path]::Combine($project, 'build')) -Force)
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/generate_random_body.py" "$linuxProject/build/random_body.inc"
    if ($LASTEXITCODE -ne 0) { throw 'Random test generation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc -march=rv32i -mabi=ilp32 -nostdlib -nostartfiles '-Wl,--no-relax' -I "$linuxProject/build" -T "$linuxProject/sw/link.ld" -o "$linuxProject/build/core_selftest.elf" "$linuxProject/sw/core_selftest.S"
    if ($LASTEXITCODE -ne 0) { throw 'Self-test firmware compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linuxProject/build/core_selftest.elf" "$linuxProject/build/core_selftest.bin"
    if ($LASTEXITCODE -ne 0) { throw 'Binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/bin_to_hex.py" "$linuxProject/build/core_selftest.bin" "$linuxProject/build/core_selftest.hex"
    if ($LASTEXITCODE -ne 0) { throw 'Memory image conversion failed.' }
    $disassembly = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objdump -d "$linuxProject/build/core_selftest.elf"
    if ($LASTEXITCODE -ne 0) { throw 'Disassembly failed.' }
    $disassembly | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'core_selftest.dis')) -Encoding utf8BOM
} catch {
    Write-Error $_
    exit 1
}
