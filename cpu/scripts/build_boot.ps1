param([string]$Out = '', [string]$Toolchain = '')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $build = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $build -Force)

    # Native RISC-V toolchain (xPack GNU RISC-V Embedded GCC). The WSL-based
    # toolchain is not available on every machine, so prefer a local install.
    if ([string]::IsNullOrWhiteSpace($Toolchain)) {
        $Toolchain = $env:RV32_TOOLCHAIN
    }
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($Toolchain)) { $candidates += $Toolchain }
    $candidates += @('H:/ST/RV32I', 'D:/ST/RV32I')
    $prefix = $null
    foreach ($candidate in $candidates) {
        $exe = [System.IO.Path]::Combine($candidate, 'bin', 'riscv-none-elf-gcc.exe')
        if (Test-Path -LiteralPath $exe -PathType Leaf) { $prefix = [System.IO.Path]::Combine($candidate, 'bin', 'riscv-none-elf-'); break }
    }
    if (-not $prefix) { throw 'No native riscv-none-elf toolchain found; set RV32_TOOLCHAIN.' }
    Write-Output "Toolchain: $prefix"

    $elf = [System.IO.Path]::Combine($build, 'bootloader.elf')
    $bin = [System.IO.Path]::Combine($build, 'bootloader.bin')
    $map = [System.IO.Path]::Combine($build, 'bootloader.map')
    $hexPath = if ($Out) { [System.IO.Path]::GetFullPath($Out) } else { [System.IO.Path]::Combine($build, 'bootloader.hex') }

    $sources = @(
        [System.IO.Path]::Combine($project, 'sw', 'boot', 'boot_start.S'),
        [System.IO.Path]::Combine($project, 'sw', 'boot', 'bootloader.c')
    )
    # _zifencei is needed only because the bootloader issues fence.i to flush
    # the write-back d-cache and invalidate the i-cache before launching.
    & "${prefix}gcc" -march=rv32i_zifencei -mabi=ilp32 -msmall-data-limit=0 -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles '-Wl,--no-relax' "-Wl,-Map,$map" -T ([System.IO.Path]::Combine($project, 'sw', 'boot', 'boot_link.ld')) -o $elf $sources -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'Bootloader compilation failed.' }
    & "${prefix}objcopy" -O binary $elf $bin
    if ($LASTEXITCODE -ne 0) { throw 'Bootloader binary conversion failed.' }
    & python ([System.IO.Path]::Combine($PSScriptRoot, 'bin_to_hex.py')) $bin $hexPath --bytes 65536
    if ($LASTEXITCODE -ne 0) { throw 'Bootloader memory image conversion failed.' }
    & "${prefix}objdump" -d $elf | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, 'bootloader.dis')) -Encoding utf8
    $size = (Get-Item -LiteralPath $bin).Length
    if ($size -gt 4096) { throw "Bootloader is $size bytes, larger than the 4 KB boot region." }
    Write-Output ("Bootloader: {0} ({1} bytes) -> {2}" -f $bin, $size, $hexPath)
} catch {
    Write-Error $_
    exit 1
}
