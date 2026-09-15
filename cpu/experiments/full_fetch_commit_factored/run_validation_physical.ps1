param([ValidateRange(1,32)][int]$PlacementSeed = 1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { throw 'Another PDS implementation is running.' }
    if ((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory -lt 3670016) { throw 'Insufficient commit headroom for PDS.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_fetch_regressions.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Fetch functional or core prerequisite failed.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_fetch_shorts.py'))
    if ($LASTEXITCODE -ne 0) { throw 'Clock source, firmware or short-run prerequisite failed.' }
    $firmware = [IO.Path]::Combine($PSScriptRoot, 'firmware', 'coremark_v1_i6000_p2700000_f153000000_rv32gcc_rv32im_O3_unroll_relax.hex')
    if ((Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash -ne '9ECD2172E0412543BB5D55E386D77549B8817F7602ACD2F0D0591F7306BD1FE5') { throw 'Physical firmware changed.' }
    $configuration = Get-Content -LiteralPath ([IO.Path]::Combine($PSScriptRoot, 'configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    $parameters = @{ FirmwareHex = $firmware; UartProfile = 'RemoteLab'; UartBaud = 115200; PlacementSeed = $PlacementSeed }
    foreach ($name in @('Predictor', 'CacheEnabled', 'LoadUseBubble', 'FastICacheHit', 'FastDCacheRead', 'FastDCacheWrite', 'FetchOverlap', 'DataOverlap', 'EarlyDRequest', 'EnableM', 'CacheSetBits', 'ICacheSetBits', 'BtbIndexBits', 'ClockHz')) {
        $parameters[$name] = $configuration.$name
    }
    & ([IO.Path]::Combine($PSScriptRoot, 'scripts', 'run_pds.ps1')) @parameters
    if ($LASTEXITCODE -ne 0) { throw 'Clock PDS build or timing audit failed; retain its artifacts.' }
} catch {
    Write-Error $_
    exit 1
}
