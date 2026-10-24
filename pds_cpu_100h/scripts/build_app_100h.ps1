param(
    [ValidateSet('hello','selftest','irqprobe','regprobe')][string]$App = 'hello',
    [switch]$ExternalUart,
    [string]$Out = '',
    [string]$Toolchain = ''
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    # Build a RAM-resident application image (linked at 0x1000) that the
    # ZBOOT console loads over UART with the 'R' command. No WSL needed.
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $cpuProject = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..', 'cpu'))
    $build = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $build -Force)

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
    Write-Output "Toolchain: $prefix"

    $swRoot = [System.IO.Path]::Combine($cpuProject, 'sw')
    $elf = [System.IO.Path]::Combine($build, "app_$App.elf")
    $bin = if ($Out) { [System.IO.Path]::GetFullPath($Out) } else { [System.IO.Path]::Combine($build, "app_$App.bin") }
    $map = [System.IO.Path]::Combine($build, "app_$App.map")

    $sources = @([System.IO.Path]::Combine($swRoot, 'start.S'))
    $appSource = switch ($App) {
        'hello'    { [System.IO.Path]::Combine($swRoot, 'app_hello.c') }
        'selftest' { [System.IO.Path]::Combine($swRoot, 'soc_selftest.c') }
        'irqprobe' { [System.IO.Path]::Combine($project, 'sw', 'irq_probe.c') }
        'regprobe'  { [System.IO.Path]::Combine($project, 'sw', 'reg_probe.c') }
    }
    $sources += $appSource
    # EXTERNAL_UART=0: external interrupt comes from KEY1 (gpio bit0), matching
    # the 100H top's gpio_input wiring. zicsr: start.S writes mtvec; the CPU
    # implements Zicsr (rv32_machine). Older toolchains folded it into rv32i,
    # xPack GCC 15 requires it explicitly.
    & "${prefix}gcc" -march=rv32i_zicsr_zifencei -mabi=ilp32 -msmall-data-limit=0 "-DEXTERNAL_UART=$(if ($ExternalUart) { 1 } else { 0 })" -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles '-Wl,--no-relax' "-Wl,-Map,$map" -I $swRoot -T ([System.IO.Path]::Combine($swRoot, 'link_soc.ld')) -o $elf $sources -lgcc
    if ($LASTEXITCODE -ne 0) { throw "App ($App) compilation failed." }
    & "${prefix}objcopy" -O binary $elf $bin
    if ($LASTEXITCODE -ne 0) { throw 'Binary conversion failed.' }
    & "${prefix}objdump" -d $elf | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, "app_$App.dis")) -Encoding utf8
    $size = (Get-Item -LiteralPath $bin).Length
    if ($size -gt 61440) { throw "App is $size bytes, larger than the 60 KB application region." }
    Write-Output ("App ($App): {0} ({1} bytes) -> {2}" -f $elf, $size, $bin)
} catch {
    Write-Error $_
    exit 1
}
