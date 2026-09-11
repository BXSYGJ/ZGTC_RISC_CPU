param([ValidateSet(27000000,157500000)][int]$ClockHz = 27000000, [ValidateRange(0,10000000)][int]$ConsoleDelayCycles = 400000, [ValidateRange(200,100000)][int]$SampleCycles = 216, [ValidateRange(10000,10000000000)][long]$TimeoutCycles = 810000000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    if (-not $PSBoundParameters.ContainsKey('SampleCycles')) { $SampleCycles = [int]($ClockHz / 125000) }
    if (-not $PSBoundParameters.ContainsKey('TimeoutCycles')) { $TimeoutCycles = 30L * $ClockHz }
    if (-not $PSBoundParameters.ContainsKey('ConsoleDelayCycles')) { $ConsoleDelayCycles = [int]([math]::Round(400000.0 * $ClockHz / 27000000)) }
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    [void](New-Item -ItemType Directory -Path ([System.IO.Path]::Combine($project,'build')) -Force)
    $linux = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $name = "scope_p${ConsoleDelayCycles}_s${SampleCycles}_t${TimeoutCycles}_rv32gcc"
    if ($ClockHz -ne 27000000) { $name += "_f$ClockHz" }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc -march=rv32i -mabi=ilp32 -msmall-data-limit=0 -std=c11 -O2 -ffreestanding -fno-builtin -Wall -Wextra -Werror -nostdlib -nostartfiles "-DCONSOLE_DELAY_CYCLES=$ConsoleDelayCycles" "-DAPP_SAMPLE_CYCLES=$SampleCycles" "-DAPP_TIMEOUT_CYCLES=${TimeoutCycles}ull" "-DAPP_CLOCK_HZ=${ClockHz}u" '-Wl,--no-relax' -T "$linux/sw/link_soc.ld" -o "$linux/build/$name.elf" "$linux/sw/start.S" "$linux/sw/scope.c" -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'Scope compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linux/build/$name.elf" "$linux/build/$name.bin"
    if ($LASTEXITCODE -ne 0) { throw 'Scope binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linux/scripts/bin_to_hex.py" "$linux/build/$name.bin" "$linux/build/$name.hex" --bytes 65536
    if ($LASTEXITCODE -ne 0) { throw 'Scope image conversion failed.' }
    $manifest = [ordered]@{RunName=$name; SampleCycles=$SampleCycles; TimeoutCycles=$TimeoutCycles; ConsoleDelayCycles=$ConsoleDelayCycles; ClockHz=$ClockHz; RecommendedUartBaud=9600; Hex=[System.IO.Path]::Combine($project,'build',"$name.hex")}
    $manifest['EnableM'] = 0
    $manifest['HexSha256'] = (Get-FileHash -LiteralPath $manifest.Hex -Algorithm SHA256).Hash
    $manifest['SourceHashes'] = [ordered]@{}
    foreach ($relative in @('sw/scope.c','sw/platform.h','sw/start.S','sw/link_soc.ld','scripts/bin_to_hex.py','scripts/build_scope.ps1')) {
        $manifest.SourceHashes[$relative] = (Get-FileHash -LiteralPath ([IO.Path]::Combine($project,$relative)) -Algorithm SHA256).Hash
    }
    $manifest['Toolchain'] = [ordered]@{ Target=$toolchain.Target; Version=$toolchain.Version; Prefix=$toolchain.Prefix }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"$name.build.json")) -Encoding utf8BOM
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','scope-latest.json')) -Encoding utf8BOM
} catch {
    Write-Error $_
    exit 1
}
