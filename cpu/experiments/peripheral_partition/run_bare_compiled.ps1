param([Parameter(Mandatory=$true)][ValidatePattern('^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')][string]$BuildName)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [IO.Path]::GetFullPath([IO.Path]::Combine($PSScriptRoot,'..','..'))
    $build = [IO.Path]::Combine($root,'build','peripheral-partition',$BuildName)
    $destination = [IO.Path]::Combine($build,'compiled')
    if (Test-Path -LiteralPath $destination) { throw 'Compiled run already exists; inspect actual process and files' }
    $manifest = Get-Content -LiteralPath ([IO.Path]::Combine($build,'manifest.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if ($manifest.Profile -ne 'NoMmioPeripherals' -or $manifest.Iterations -notin @(10,6000) -or $manifest.FullScoreQualified) { throw 'Wrong independently measured input' }
    if ($manifest.ClockHz -notin @(144000000,146250000,148500000,157500000)) { throw 'Unsupported simulator clock' }
    $clockFlags = @($manifest.CompilerFlags | Where-Object { $_.StartsWith('-DCPU_CLOCK_HZ=') })
    if ($clockFlags.Count -ne 1 -or $clockFlags[0] -ne ('-DCPU_CLOCK_HZ='+$manifest.ClockHz+'u')) { throw 'Firmware compiler clock mismatch' }
    $cycleLimit = if ($manifest.Iterations -eq 10) { '10000000' } else { '6000000000' }
    foreach ($relative in $manifest.SourceHashes.Keys) {
        $actual = if ($relative.Contains('/')) { [IO.Path]::Combine($root,$relative) } else { [IO.Path]::Combine($build,$relative) }
        if ((Get-FileHash -LiteralPath $actual).Hash -ne $manifest.SourceHashes[$relative]) { throw ('Captured input changed: '+$relative) }
    }
    if ((Get-FileHash -LiteralPath ([IO.Path]::Combine($build,'coremark.hex'))).Hash -ne $manifest.FirmwareSha256) { throw 'Captured firmware changed' }
    [void](New-Item -ItemType Directory -Path $destination)
    foreach ($name in @('rv32_bare_sim.sv','bare_compiled.cpp','run_bare_compiled.ps1')) { Copy-Item -LiteralPath ([IO.Path]::Combine($PSScriptRoot,$name)) -Destination ([IO.Path]::Combine($destination,$name)) }
    $linuxBuild = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $build).Trim()
    if ($LASTEXITCODE) { throw 'Build path conversion failed' }
    $linuxDestination = $linuxBuild+'/compiled'
    $rtl = @(Get-ChildItem -LiteralPath $build -Filter '*.sv' -File | Where-Object { $_.Name -ne 'coremark_bare_tb.sv' } | ForEach-Object { $linuxBuild+'/'+$_.Name })
    $firmwareParameter = '-GINIT_FILE="'+$linuxBuild+'/coremark.hex"'
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/verilator --cc --exe --build --Wall -Wno-fatal -j 2 --top-module rv32_bare_sim --Mdir ($linuxDestination+'/obj') -CFLAGS '-O3 -std=c++14' ('-GCLOCK_HZ='+$manifest.ClockHz) $firmwareParameter @rtl ($linuxDestination+'/rv32_bare_sim.sv') ($linuxDestination+'/bare_compiled.cpp') *> ([IO.Path]::Combine($destination,'compile.log'))
    if ($LASTEXITCODE) { throw 'Bare compiled model build failed' }
    $hashes = [ordered]@{}
    foreach ($name in @('rv32_bare_sim.sv','bare_compiled.cpp','run_bare_compiled.ps1','compile.log','obj/Vrv32_bare_sim')) { $hashes[$name]=(Get-FileHash -LiteralPath ([IO.Path]::Combine($destination,$name))).Hash }
    [ordered]@{Schema=1;ClockHz=$manifest.ClockHz;ParentManifestSha256=(Get-FileHash -LiteralPath ([IO.Path]::Combine($build,'manifest.json'))).Hash;Artifacts=$hashes;HardwareValidated=$false;ObservationInterface='simulation-only direct RAM read port; not physical resource proof'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ([IO.Path]::Combine($destination,'manifest.json')) -Encoding utf8BOM
    & wsl.exe --distribution Ubuntu-22.04 --exec ($linuxDestination+'/obj/Vrv32_bare_sim') ($linuxDestination+'/coremark.output') ($linuxDestination+'/result.json') $manifest.ResultAddress $cycleLimit *> ([IO.Path]::Combine($destination,'execute.log'))
    if ($LASTEXITCODE) { throw 'Bare compiled runtime failed' }
    Get-Content -LiteralPath ([IO.Path]::Combine($destination,'execute.log')) -Encoding utf8
} catch {
    Write-Error $_
    exit 1
}
