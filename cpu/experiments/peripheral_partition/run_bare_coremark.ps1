param([switch]$ValidationRun, [switch]$BuildOnly, [ValidateSet(10,6000)][int]$Iterations = 10, [ValidateSet(144000000,146250000,148500000,157500000)][int]$ClockHz = 157500000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    . ([IO.Path]::Combine($root,'scripts','riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $run = (Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+([guid]::NewGuid().ToString('N').Substring(0,8))
    $build = [IO.Path]::Combine($root,'build','peripheral-partition',$run)
    [void](New-Item -ItemType Directory -Path $build -Force)
    $linuxBuild = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $build).Trim()
    if ($LASTEXITCODE) { throw 'Build path conversion failed' }
    $linuxRoot = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $root).Trim()
    if ($LASTEXITCODE) { throw 'Root path conversion failed' }
    $hashes = [ordered]@{}
    $sources = [System.Collections.Generic.List[string]]::new()
    $upstreamLockPath = [IO.Path]::Combine($PSScriptRoot,'upstream-lock.json')
    if ((Get-FileHash -LiteralPath $upstreamLockPath).Hash -ne 'F87C6646F53EC181D4A5B9BD4F5B84D6D8589E0840E6A91236D07273514B90C8') { throw 'Pinned upstream lock changed' }
    $upstreamLock = Get-Content -LiteralPath $upstreamLockPath -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    $upstreamFiles = @('core_list_join.c','core_main.c','core_matrix.c','core_state.c','core_util.c','coremark.h')
    foreach ($name in $upstreamFiles) {
        $actual = [IO.Path]::Combine($root,'build','coremark-upstream',$name)
        if ((Get-FileHash -LiteralPath $actual).Hash -ne $upstreamLock.files[$name]) { throw ('Pinned upstream source changed: '+$name) }
        Copy-Item -LiteralPath $actual -Destination ([IO.Path]::Combine($build,$name))
        $hashes[$name]=(Get-FileHash -LiteralPath $actual).Hash
        if ($name.EndsWith('.c')) { $sources.Add($linuxBuild+'/'+$name) }
    }
    $portFiles = @('core_portme.c','ee_printf.c','results.h','rv32_soc.sv','coremark_bare_tb.sv','run_bare_coremark.ps1')
    foreach ($name in $portFiles) {
        $actual = [IO.Path]::Combine($PSScriptRoot,$name)
        Copy-Item -LiteralPath $actual -Destination ([IO.Path]::Combine($build,$name))
        $hashes[$name]=(Get-FileHash -LiteralPath $actual).Hash
    }
    foreach ($relative in @('sw/platform.h','sw/coremark/core_portme.h','sw/start.S','sw/link_soc.ld','scripts/bin_to_hex.py')) {
        $actual = [IO.Path]::Combine($root,$relative)
        $hashes[$relative]=(Get-FileHash -LiteralPath $actual).Hash
    }
    $mode = [int][bool]$ValidationRun
    $performance = 1-$mode
    $flags = @('-march=rv32im','-mabi=ilp32','-msmall-data-limit=0','-std=c11','-O3','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-DITERATIONS=10',('-DVALIDATION_RUN='+$mode),('-DPERFORMANCE_RUN='+$performance),'-DTOTAL_DATA_SIZE=2000','-funroll-loops','-DCONSOLE_DELAY_CYCLES=0',('-DCPU_CLOCK_HZ='+$ClockHz+'u'),'-Wl,--relax')
    $flags = @($flags | ForEach-Object { if ($_ -eq '-DITERATIONS=10') { '-DITERATIONS='+$Iterations } else { $_ } })
    if ($Iterations -ne 10 -and -not $BuildOnly) { throw 'Full-duration firmware uses compiled simulation; specify BuildOnly' }
    $flagsText = '-DFLAGS_STR="'+($flags -join ' ')+'"'
    $sources.Add($linuxRoot+'/sw/start.S')
    $sources.Add($linuxRoot+'/experiments/peripheral_partition/core_portme.c')
    $sources.Add($linuxRoot+'/experiments/peripheral_partition/ee_printf.c')
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc @flags $flagsText -I ($linuxRoot+'/sw/coremark') -I $linuxBuild -T ($linuxRoot+'/sw/link_soc.ld') -o ($linuxBuild+'/coremark.elf') @sources -lgcc
    if ($LASTEXITCODE) { throw 'Bare CoreMark compilation failed' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary ($linuxBuild+'/coremark.elf') ($linuxBuild+'/coremark.bin')
    if ($LASTEXITCODE) { throw 'Bare firmware conversion failed' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 ($linuxRoot+'/scripts/bin_to_hex.py') ($linuxBuild+'/coremark.bin') ($linuxBuild+'/coremark.hex') --bytes 65536
    if ($LASTEXITCODE) { throw 'Bare firmware HEX conversion failed' }
    $symbols = & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Nm -S ($linuxBuild+'/coremark.elf')
    if ($LASTEXITCODE) { throw 'Result symbol lookup failed' }
    $symbol = @($symbols | Where-Object { $_ -match '^([0-9a-fA-F]+) [0-9a-fA-F]+ [Bb] benchmark_result$' })
    if ($symbol.Count -ne 1) { throw 'Ambiguous result symbol' }
    $address = $symbol[0].Split(' ')[0]
    $symbols | Set-Content -LiteralPath ([IO.Path]::Combine($build,'symbols.txt')) -Encoding utf8BOM
    $rtl = [System.Collections.Generic.List[string]]::new()
    foreach ($file in Get-ChildItem -LiteralPath ([IO.Path]::Combine($root,'build','regfile-valid-fanout-stage','rtl')) -Filter '*.sv' -File) {
        if ($file.Name -in @('rv32_soc.sv','rv32_peripherals.sv','rv32_uart.sv','rv32_board_top.sv')) { continue }
        Copy-Item -LiteralPath $file.FullName -Destination ([IO.Path]::Combine($build,$file.Name))
        $hashes[$file.Name]=(Get-FileHash -LiteralPath $file.FullName).Hash
        $rtl.Add($linuxBuild+'/'+$file.Name)
    }
    if ($hashes['rv32_core.sv'] -ne 'DC90363D426754F032EC04DB6F4BE76DA439CCA149E372853EE2D64536D20FCE') { throw 'Bare candidate CPU drifted' }
    $rtl.Add($linuxBuild+'/rv32_soc.sv')
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/iverilog -g2012 -s coremark_bare_tb ('-Pcoremark_bare_tb.CLOCK_HZ='+$ClockHz) -o ($linuxBuild+'/bare.vvp') @rtl ($linuxBuild+'/coremark_bare_tb.sv') *> ([IO.Path]::Combine($build,'compile.log'))
    if ($LASTEXITCODE) { throw 'Bare RTL compilation failed' }
    $manifest = [ordered]@{Schema=1;Profile='NoMmioPeripherals';ClockHz=$ClockHz;Iterations=10;ValidationRun=[bool]$ValidationRun;SourceHashes=$hashes;FirmwareSha256=(Get-FileHash -LiteralPath ([IO.Path]::Combine($build,'coremark.hex'))).Hash;CompilerFlags=$flags;ResultAddress=$address;HardwareValidated=$false;FullScoreQualified=$false;ToolchainTarget=$toolchain.Target;ToolchainVersion=$toolchain.Version}
    $manifest.Iterations = $Iterations
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath ([IO.Path]::Combine($build,'manifest.json')) -Encoding utf8BOM
    [ordered]@{RunName=$run;Iterations=$Iterations;ValidationRun=[bool]$ValidationRun;ClockHz=$ClockHz;HexSha256=$manifest.FirmwareSha256;EnableM=1;Isa='rv32im';Application='coremark_no_mmio_peripherals'} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ([IO.Path]::Combine($build,'coremark.build.json')) -Encoding utf8BOM
    Write-Output ('Bare simulation: '+$build)
    if ($BuildOnly) { Write-Output 'Firmware and RTL compiled; runtime not started'; exit 0 }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/vvp ($linuxBuild+'/bare.vvp') ('+firmware='+$linuxBuild+'/coremark.hex') ('+output='+$linuxBuild+'/coremark.output') ('+result='+$linuxBuild+'/result.json') ('+result_address='+$address) *> ([IO.Path]::Combine($build,'execute.log'))
    if ($LASTEXITCODE) { throw 'Bare CoreMark runtime failed' }
    Get-Content -LiteralPath ([IO.Path]::Combine($build,'execute.log')) -Encoding utf8
} catch {
    Write-Error $_
    exit 1
}
