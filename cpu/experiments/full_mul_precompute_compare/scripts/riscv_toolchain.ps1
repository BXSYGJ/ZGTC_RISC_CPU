[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
function Get-RiscvToolchain {
    param()
    try {
        $project=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
        $manifestPath=[System.IO.Path]::Combine($project,'build','riscv32-toolchain.json')
        if(-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Build the genuine RV32 toolchain with cpu/scripts/build_riscv32_toolchain.ps1 first.' }
        $manifest=Get-Content -LiteralPath $manifestPath -Raw -ErrorAction Stop | ConvertFrom-Json
        if($manifest.Target -ne 'riscv32-unknown-elf' -or $manifest.Arch -ne 'rv32i' -or $manifest.Abi -ne 'ilp32' -or $manifest.CompilerVersion -ne '10.2.0') { throw 'Toolchain manifest has an unsupported target, ISA, ABI or version.' }
        $prefix=[string]$manifest.ToolPrefix
        if($prefix -notmatch '^/home/[A-Za-z0-9/._-]+/bin/riscv32-unknown-elf-$' -or ($prefix.Split('/') -contains '..')) { throw 'Invalid toolchain prefix.' }
        $target=(& wsl.exe --distribution Ubuntu-22.04 --exec "${prefix}gcc" -dumpmachine).Trim()
        if($LASTEXITCODE -or $target -ne 'riscv32-unknown-elf') { throw 'Live compiler target differs from the recorded RV32 target.' }
        $version=(& wsl.exe --distribution Ubuntu-22.04 --exec "${prefix}gcc" -dumpfullversion).Trim()
        if($LASTEXITCODE -or $version -ne $manifest.CompilerVersion) { throw 'Live compiler version differs from the recorded version.' }
        return [pscustomobject]@{Target=$target;Version=$manifest.CompilerVersion;Prefix=$prefix;Gcc="${prefix}gcc";Objcopy="${prefix}objcopy";Objdump="${prefix}objdump";Readelf="${prefix}readelf";Nm="${prefix}nm"}
    } catch {
        throw
    }
}
