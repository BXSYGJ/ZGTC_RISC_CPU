param([ValidateSet(27000000,120000000,157500000)][int]$ClockHz = 120000000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot, 'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $build = [System.IO.Path]::Combine($project, 'build', 'gpio', ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)))
    [void](New-Item -ItemType Directory -Path $build -Force)
    $linux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE) { throw 'Project path conversion failed.' }
    $linuxBuild = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $build).Trim()
    if ($LASTEXITCODE) { throw 'Build path conversion failed.' }
    $inputs = [ordered]@{}
    foreach ($source in @('sw/gpio_diagnostic.c', 'sw/platform.h', 'sw/start.S', 'sw/link_soc.ld', 'scripts/build_gpio.ps1', 'scripts/bin_to_hex.py', 'scripts/riscv_toolchain.ps1')) {
        $inputs[$source] = (Get-FileHash -LiteralPath ([System.IO.Path]::Combine($project, $source)) -Algorithm SHA256).Hash
    }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc -march=rv32i -mabi=ilp32 -msmall-data-limit=0 -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles '-Wl,--no-relax' -T "$linux/sw/link_soc.ld" -o "$linuxBuild/gpio_diagnostic.elf" "$linux/sw/start.S" "$linux/sw/gpio_diagnostic.c" -lgcc
    if ($LASTEXITCODE) { throw 'GPIO firmware compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linuxBuild/gpio_diagnostic.elf" "$linuxBuild/gpio_diagnostic.bin"
    if ($LASTEXITCODE) { throw 'GPIO binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linux/scripts/bin_to_hex.py" "$linuxBuild/gpio_diagnostic.bin" "$linuxBuild/gpio_diagnostic.hex" --bytes 65536
    if ($LASTEXITCODE) { throw 'GPIO image conversion failed.' }
    foreach ($source in $inputs.Keys) {
        if ($inputs[$source] -ne (Get-FileHash -LiteralPath ([System.IO.Path]::Combine($project, $source)) -Algorithm SHA256).Hash) { throw "Build input changed: $source" }
    }
    $hexPath = [System.IO.Path]::Combine($build, 'gpio_diagnostic.hex')
    $manifest = [ordered]@{ Application='gpio_diagnostic'; ClockHz=$ClockHz; ClockIndependentCode=$true; EnableM=0; RecommendedUartBaud=115200; Hex=$hexPath; HexSha256=(Get-FileHash -LiteralPath $hexPath -Algorithm SHA256).Hash; SourceHashes=$inputs; Toolchain=$toolchain; GeneratedUtc=[DateTime]::UtcNow.ToString('o') }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::ChangeExtension($hexPath, '.build.json')) -Encoding utf8BOM
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project, 'build', 'gpio-latest.json')) -Encoding utf8BOM
    Write-Output "GPIO firmware: $hexPath"
} catch {
    Write-Error $_
    exit 1
}
