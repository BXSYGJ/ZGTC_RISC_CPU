param([string]$Source = '', [string]$Name = '', [string]$Toolchain = '', [string]$March = 'rv32i_zicsr_zifencei')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $build = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $build -Force)
    if ([string]::IsNullOrWhiteSpace($Source)) { $Source = [System.IO.Path]::Combine($project, 'sw', 'app_hello.c') }
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) { throw "Application source does not exist: $Source" }
    if ([string]::IsNullOrWhiteSpace($Name)) { $Name = [System.IO.Path]::GetFileNameWithoutExtension($Source) }

    if ([string]::IsNullOrWhiteSpace($Toolchain)) { $Toolchain = $env:RV32_TOOLCHAIN }
    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($Toolchain)) { $candidates += $Toolchain }
    $candidates += @('H:/ST/RV32I', 'D:/ST/RV32I')
    $prefix = $null
    foreach ($candidate in $candidates) {
        $exe = [System.IO.Path]::Combine($candidate, 'bin', 'riscv-none-elf-gcc.exe')
        if (Test-Path -LiteralPath $exe -PathType Leaf) { $prefix = [System.IO.Path]::Combine($candidate, 'bin', 'riscv-none-elf-'); break }
    }
    if (-not $prefix) { throw 'No native riscv-none-elf toolchain found; set RV32_TOOLCHAIN.' }

    $elf = [System.IO.Path]::Combine($build, "$Name.elf")
    $bin = [System.IO.Path]::Combine($build, "$Name.bin")
    $map = [System.IO.Path]::Combine($build, "$Name.map")
    $start = [System.IO.Path]::Combine($project, 'sw', 'start.S')
    $ld = [System.IO.Path]::Combine($project, 'sw', 'link_soc.ld')
    & "${prefix}gcc" "-march=$March" -mabi=ilp32 -msmall-data-limit=0 -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles '-Wl,--no-relax' "-Wl,-Map,$map" -T $ld -o $elf $start $Source -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'Application compilation failed.' }
    & "${prefix}objcopy" -O binary $elf $bin
    if ($LASTEXITCODE -ne 0) { throw 'Application binary conversion failed.' }
    $size = (Get-Item -LiteralPath $bin).Length
    if ($size -gt 61440) { throw "Application is $size bytes, larger than the 60 KB BRAM region." }
    & "${prefix}objdump" -d $elf | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, "$Name.dis")) -Encoding utf8
    Write-Output ("Application: {0} ({1} bytes) -> {2}" -f $elf, $size, $bin)
} catch {
    Write-Error $_
    exit 1
}
