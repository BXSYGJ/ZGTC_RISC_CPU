[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Target, [string]$FixtureRoot = $PSScriptRoot)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $expectedTarget = [System.IO.Path]::Combine($FixtureRoot, 'rollback_copy.v')
    $resolvedTarget = [System.IO.Path]::GetFullPath($Target)
    if ($resolvedTarget -ne [System.IO.Path]::GetFullPath($expectedTarget)) { throw 'Only the isolated rollback fixture is permitted' }
    $source = [System.IO.Path]::Combine($FixtureRoot, 'BASELINE.v')
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c29dc11ede3b716f48c5e52aa097ec5cefa873dc205f3a056ebaac7c6bc745e8') { throw 'Baseline hash mismatch' }
    Copy-Item -LiteralPath $source -Destination $resolvedTarget -Force -ErrorAction Stop
    if ((Get-FileHash -LiteralPath $resolvedTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'c29dc11ede3b716f48c5e52aa097ec5cefa873dc205f3a056ebaac7c6bc745e8') { throw 'Restored hash mismatch' }
    Write-Output 'ROLLBACK_RESTORED original_sha256=c29dc11ede3b716f48c5e52aa097ec5cefa873dc205f3a056ebaac7c6bc745e8'
    exit 0
} catch { Write-Error $_; exit 1 }
