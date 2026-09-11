param([ValidateRange(1,32)][int]$PlacementSeed = 1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { throw 'Another PDS implementation is running.' }
    if ((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory -lt 3670016) { throw 'Insufficient commit headroom for PDS.' }
    $project = [IO.Path]::Combine($PSScriptRoot, 'build', 'physical-project-width16')
    if (Test-Path -LiteralPath $project) { throw 'Physical staging already exists; inspect its existing runs instead of restarting.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'stage_timer_physical.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Source-bound peripheral staging failed.' }
    $screenPath = [IO.Path]::Combine($PSScriptRoot, 'screen.py')
    if ($screenPath -notmatch '^[A-Za-z]:') { throw 'Expected a drive-rooted screen path.' }
    $linuxScript = '/mnt/' + $screenPath.Substring(0, 1).ToLowerInvariant() + $screenPath.Substring(2).Replace([IO.Path]::DirectorySeparatorChar, '/')
    & wsl.exe --exec python3 $linuxScript --attempt width16
    if ($LASTEXITCODE -ne 0) { throw 'V0 timer full-SoC screen failed.' }
    & wsl.exe --exec python3 $linuxScript --validation --attempt width16
    if ($LASTEXITCODE -ne 0) { throw 'V1 timer full-SoC screen failed.' }
    $base = [IO.Path]::Combine($PSScriptRoot, '..', 'full_redirect_clock151200')
    $configuration = Get-Content -LiteralPath ([IO.Path]::Combine($base, 'configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    $firmware = [IO.Path]::Combine($PSScriptRoot, '..', 'full_mul_precompute_clock154285', 'build', 'coremark_v0_i6000_p2700000_f151200000_rv32gcc_rv32im_O3_unroll_relax.hex')
    if ((Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash -ne '3A82C84E665E212C8BC8CF492CD169D7A579BF20146F810FA104F51EAE61287B') { throw 'Physical firmware changed.' }
    $parameters = @{ FirmwareHex = $firmware; UartProfile = 'RemoteLab'; UartBaud = 115200; PlacementSeed = $PlacementSeed }
    foreach ($name in @('Predictor', 'CacheEnabled', 'LoadUseBubble', 'FastICacheHit', 'FastDCacheRead', 'FastDCacheWrite', 'FetchOverlap', 'DataOverlap', 'EarlyDRequest', 'EnableM', 'CacheSetBits', 'ICacheSetBits', 'BtbIndexBits', 'ClockHz')) {
        $parameters[$name] = $configuration.$name
    }
    & ([IO.Path]::Combine($project, 'scripts', 'run_pds.ps1')) @parameters
    if ($LASTEXITCODE -ne 0) { throw 'Ordinary PDS implementation failed; retain all run evidence.' }
} catch {
    Write-Error $_
    exit 1
}
