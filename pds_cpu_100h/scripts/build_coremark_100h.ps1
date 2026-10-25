param(
    [ValidateRange(1,10000000)][int]$Iterations = 1000,
    [ValidateRange(0,1)][int]$EnableM = 1,
    [ValidateSet('O2','O3','Os')][string]$Optimization = 'O2',
    [ValidateSet(27000000,54000000,60000000,67500000,72000000,75600000,81000000,90000000,99000000,102600000,108000000,120000000,126000000,132000000,135000000,153000000,155520000,162000000,180000000,194400000,216000000,270000000)][int]$ClockHz = 27000000,
    [string]$Out = '',
    [string]$Toolchain = ''
)
# Native (no-WSL) CoreMark build for the PG2L100H serial-boot flow.
# Mirrors cpu/scripts/build_coremark.ps1 flags; links at 0x1000 (link_soc.ld)
# so the ZBOOT console can load it over UART.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $cpuProject = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..', 'cpu'))
    $build = [System.IO.Path]::Combine($project, 'build')
    [void](New-Item -ItemType Directory -Path $build -Force)

    # upstream CoreMark, pinned revision + clean tree (same policy as the 200H flow)
    $upstream = [System.IO.Path]::Combine($cpuProject, 'build', 'coremark-upstream')
    $revision = '1f483d5b8316753a742cbf5590caf5bd0a4e4777'
    if (-not (Test-Path -LiteralPath $upstream)) { throw "Upstream CoreMark not found at $upstream" }
    $actual = (& git -C $upstream rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $revision) { throw "Cached upstream does not match the pinned revision; not using it." }
    $changes = & git -C $upstream status --porcelain
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Upstream checkout is modified; benchmark sources must remain unchanged.' }

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

    # zicsr: mcycle/minstret/mcause CSRs; zifencei: fence.i in start.S/trap paths
    $isa = if ($EnableM) { 'rv32im_zicsr_zifencei' } else { 'rv32i_zicsr_zifencei' }
    $runName = "coremark_v0_i$Iterations"
    if ($ClockHz -ne 27000000) { $runName += "_f$ClockHz" }
    if ($EnableM) { $runName += '_rv32im' }
    if ($Optimization -ne 'O2') { $runName += "_$Optimization" }
    $runName += '_rv32gcc'

    $elf = [System.IO.Path]::Combine($build, "$runName.elf")
    $bin = if ($Out) { [System.IO.Path]::GetFullPath($Out) } else { [System.IO.Path]::Combine($build, "$runName.bin") }
    $map = [System.IO.Path]::Combine($build, "$runName.map")

    $flags = @(
        "-march=$isa", '-mabi=ilp32', '-msmall-data-limit=0', '-std=c11', "-$Optimization",
        '-ffreestanding', '-fno-builtin', '-Wall', '-Wextra', '-nostdlib', '-nostartfiles',
        "-DITERATIONS=$Iterations", '-DVALIDATION_RUN=0', '-DPERFORMANCE_RUN=1',
        '-DTOTAL_DATA_SIZE=2000', '-DCONSOLE_DELAY_CYCLES=0', "-DCPU_CLOCK_HZ=${ClockHz}u"
    )
    $linkFlag = '-Wl,--no-relax'
    $flagString = '-DFLAGS_STR="' + ($flags -join ' ') + ' ' + $linkFlag + '"'
    $swRoot = [System.IO.Path]::Combine($cpuProject, 'sw')
    $sources = @(
        [System.IO.Path]::Combine($upstream, 'core_list_join.c'),
        [System.IO.Path]::Combine($upstream, 'core_main.c'),
        [System.IO.Path]::Combine($upstream, 'core_matrix.c'),
        [System.IO.Path]::Combine($upstream, 'core_state.c'),
        [System.IO.Path]::Combine($upstream, 'core_util.c'),
        [System.IO.Path]::Combine($swRoot, 'start.S'),
        [System.IO.Path]::Combine($swRoot, 'coremark', 'core_portme.c'),
        [System.IO.Path]::Combine($swRoot, 'coremark', 'ee_printf.c')
    )
    & "${prefix}gcc" @flags $flagString $linkFlag -I ([System.IO.Path]::Combine($swRoot, 'coremark')) -I $upstream -T ([System.IO.Path]::Combine($swRoot, 'link_soc.ld')) -o $elf $sources -lgcc
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark compilation failed.' }
    & "${prefix}objcopy" -O binary $elf $bin
    if ($LASTEXITCODE -ne 0) { throw 'Binary conversion failed.' }
    & "${prefix}objdump" -d $elf | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, "$runName.dis")) -Encoding utf8
    $size = (Get-Item -LiteralPath $bin).Length
    if ($size -gt 61440) { throw "CoreMark image is $size bytes, larger than the 60 KB application region." }
    $manifest = [ordered]@{
        UpstreamRevision = $revision; Iterations = $Iterations; ValidationRun = $false
        Isa = $isa; EnableM = $EnableM; Optimization = $Optimization; ClockHz = $ClockHz
        ConsoleDelayCycles = 0; Bin = $bin; BinSha256 = (Get-FileHash -LiteralPath $bin -Algorithm SHA256).Hash
        GeneratedUtc = [datetime]::UtcNow.ToString('o')
    }
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($build, 'coremark-100h-latest.json')) -Encoding utf8
    Write-Output ("CoreMark ($runName): {0} ({1} bytes) -> {2}" -f $elf, $size, $bin)
    Write-Output 'Note: score = 6000 * ClockHz / timed_cycles from the ZGTC cycle counters (see portable_fini output).'
} catch {
    Write-Error $_
    exit 1
}
