param([switch]$LinkerRelaxation, [switch]$LinkTimeOptimization, [switch]$UnrollLoops, [ValidateRange(0,1)][int]$EnableM = 0, [ValidateSet('O2','O3','Os')][string]$Optimization = 'O2', [ValidateRange(1,10000000)][int]$Iterations = 1000, [switch]$ValidationRun, [ValidateRange(0,3000000)][int]$ConsoleDelayCycles = 0, [ValidateSet(27000000,54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,120000000,126000000,132000000,135000000,141750000,144000000,146250000,148500000,151200000,154285714,157500000,162000000,180000000,194400000,216000000,270000000)][int]$ClockHz = 27000000)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    . ([System.IO.Path]::Combine($PSScriptRoot,'riscv_toolchain.ps1'))
    $toolchain = Get-RiscvToolchain
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $linuxProject = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $project).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'WSL path conversion failed.' }
    $upstream = [System.IO.Path]::Combine($project, 'build', 'coremark-upstream')
    $revision = '1f483d5b8316753a742cbf5590caf5bd0a4e4777'
    if (-not (Test-Path -LiteralPath $upstream)) {
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/git clone https://github.com/eembc/coremark.git "$linuxProject/build/coremark-upstream"
        if ($LASTEXITCODE -ne 0) { throw 'Upstream download failed.' }
        & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/git -C "$linuxProject/build/coremark-upstream" checkout --detach $revision
        if ($LASTEXITCODE -ne 0) { throw 'Pinned revision checkout failed.' }
    }
    $actual = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/git -C "$linuxProject/build/coremark-upstream" rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $revision) { throw 'Cached upstream does not match the pinned revision; not overwriting it.' }
    $changes = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/git -C "$linuxProject/build/coremark-upstream" status --porcelain
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Upstream checkout is modified; benchmark sources must remain unchanged.' }
    $mode = if ($ValidationRun) { 1 } else { 0 }
    $performance = 1 - $mode
    $runName = "coremark_v${mode}_i$Iterations"
    if ($ConsoleDelayCycles -gt 0) { $runName += "_p$ConsoleDelayCycles" }
    if ($ClockHz -ne 27000000) { $runName += "_f$ClockHz" }
    $runName += "_rv32gcc"
    $isa = if ($EnableM) { 'rv32im' } else { 'rv32i' }
    if ($EnableM) { $runName += '_rv32im' }
    if ($Optimization -ne 'O2') { $runName += "_$Optimization" }
    if ($UnrollLoops) { $runName += '_unroll' }
    if ($LinkTimeOptimization) { $runName += '_lto' }
    if ($LinkerRelaxation) { $runName += '_relax' }
    $flags = @("-march=$isa", '-mabi=ilp32', '-msmall-data-limit=0', '-std=c11', "-$Optimization", '-ffreestanding', '-fno-builtin', '-Wall', '-Wextra', '-nostdlib', '-nostartfiles', "-DITERATIONS=$Iterations", "-DVALIDATION_RUN=$mode", "-DPERFORMANCE_RUN=$performance", '-DTOTAL_DATA_SIZE=2000')
    if ($UnrollLoops) { $flags += '-funroll-loops' }
    if ($LinkTimeOptimization) { $flags += '-flto' }
    $flags += "-DCONSOLE_DELAY_CYCLES=$ConsoleDelayCycles"
    $flags += "-DCPU_CLOCK_HZ=${ClockHz}u"
    $linkFlag = if ($LinkerRelaxation) { '-Wl,--relax' } else { '-Wl,--no-relax' }
    $flagString = '-DFLAGS_STR="' + ($flags -join ' ') + ' ' + $linkFlag + '"'
    $sources = @('core_list_join.c', 'core_main.c', 'core_matrix.c', 'core_state.c', 'core_util.c') | ForEach-Object { "$linuxProject/build/coremark-upstream/$_" }
    $sources += @("$linuxProject/sw/start.S", "$linuxProject/sw/coremark/core_portme.c", "$linuxProject/sw/coremark/ee_printf.c")
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Gcc @flags $flagString $linkFlag -I "$linuxProject/sw/coremark" -I "$linuxProject/build/coremark-upstream" -T "$linuxProject/sw/link_soc.ld" -o "$linuxProject/build/$runName.elf" @sources -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark compilation failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec $toolchain.Objcopy -O binary "$linuxProject/build/$runName.elf" "$linuxProject/build/$runName.bin"
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark binary conversion failed.' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 "$linuxProject/scripts/bin_to_hex.py" "$linuxProject/build/$runName.bin" "$linuxProject/build/$runName.hex" --bytes 65536
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark image conversion failed.' }
    $manifest = [ordered]@{ UpstreamRevision=$revision; Iterations=$Iterations; ValidationRun=[bool]$ValidationRun; Flags=$flags; ExtraLinkFlags=$linkFlag; ClockHz=$ClockHz; Hex=[System.IO.Path]::Combine($project,'build',"$runName.hex"); RunName=$runName }
    $manifest['HexSha256'] = (Get-FileHash -LiteralPath $manifest.Hex -Algorithm SHA256).Hash
    $manifest['Toolchain'] = [ordered]@{ Target=$toolchain.Target; Version=$toolchain.Version; Prefix=$toolchain.Prefix }
    $manifest['Optimization'] = $Optimization
    $manifest['UnrollLoops'] = [bool]$UnrollLoops
    $manifest['LinkTimeOptimization'] = [bool]$LinkTimeOptimization
    $manifest['LinkerRelaxation'] = [bool]$LinkerRelaxation
    $manifest['ConsoleDelayCycles'] = $ConsoleDelayCycles
    $manifest['Isa'] = $isa
    $manifest['EnableM'] = $EnableM
    $manifest | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build',"$runName.build.json")) -Encoding utf8BOM
    $manifest | ConvertTo-Json | Set-Content -LiteralPath ([System.IO.Path]::Combine($project,'build','coremark-latest.json')) -Encoding utf8BOM
    Write-Output "CoreMark built: $runName (not yet a validated score)"
} catch {
    Write-Error $_
    exit 1
}
