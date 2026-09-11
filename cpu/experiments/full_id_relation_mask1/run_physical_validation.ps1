param([ValidateRange(1,32)][int]$PlacementSeed = 1)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { throw 'Another PDS implementation is running.' }
    if ((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory -lt 3670016) { throw 'Insufficient commit headroom for PDS.' }
    $project = [IO.Path]::Combine($PSScriptRoot, 'build', 'physical-project-complete')
    if (-not (Test-Path -LiteralPath $project)) { throw 'Source-bound physical staging is missing.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_full_ila.py')) binding
    if ($LASTEXITCODE -ne 0) { throw 'Existing physical source binding failed.' }
    $qualification = Get-Content -LiteralPath ([IO.Path]::Combine($PSScriptRoot, 'build', 'ila', 'id-relation-mask1-seed1', 'physical-qualification.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not $qualification.physical_timing_passed) { throw 'V0 full-system timing has not passed.' }
    $attempt = [IO.Path]::Combine($PSScriptRoot, 'build', 'validation-physical-launch.json')
    if (Test-Path -LiteralPath $attempt) { throw 'Validation launch already exists; inspect the existing process and artifacts.' }
    $base = [IO.Path]::Combine($PSScriptRoot, '..', 'full_redirect_clock151200')
    $configuration = Get-Content -LiteralPath ([IO.Path]::Combine($base, 'configuration.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    $firmware = [IO.Path]::Combine($PSScriptRoot, '..', 'full_mul_precompute_clock154285', 'build', 'coremark_v1_i6000_p2700000_f151200000_rv32gcc_rv32im_O3_unroll_relax.hex')
    if ((Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash -ne '8097947BBEA80F19DEAFA4F7AEE79A340869FC7405DAE8C85731EFA408986FAB') { throw 'Physical firmware changed.' }
    $parameters = @{ FirmwareHex = $firmware; UartProfile = 'RemoteLab'; UartBaud = 115200; PlacementSeed = $PlacementSeed }
    foreach ($name in @('Predictor', 'CacheEnabled', 'LoadUseBubble', 'FastICacheHit', 'FastDCacheRead', 'FastDCacheWrite', 'FetchOverlap', 'DataOverlap', 'EarlyDRequest', 'EnableM', 'CacheSetBits', 'ICacheSetBits', 'BtbIndexBits', 'ClockHz')) {
        $parameters[$name] = $configuration.$name
    }
    [ordered]@{ StartedUtc = [datetime]::UtcNow.ToString('o'); Firmware = $firmware; FirmwareSha256 = (Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash; PlacementSeed = $PlacementSeed } | ConvertTo-Json | Set-Content -LiteralPath $attempt -Encoding utf8BOM
    & ([IO.Path]::Combine($project, 'scripts', 'run_pds.ps1')) @parameters
    if ($LASTEXITCODE -ne 0) { throw 'Ordinary PDS implementation failed; retain all run evidence.' }
} catch {
    Write-Error $_
    exit 1
}
