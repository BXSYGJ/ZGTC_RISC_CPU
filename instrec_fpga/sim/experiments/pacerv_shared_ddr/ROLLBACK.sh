param([Parameter(Mandatory)][string]$EvidenceDirectory, [Parameter(Mandatory)][string]$TargetRtlDirectory)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    & ([System.IO.Path]::Combine($EvidenceDirectory, 'ROLLBACK.ps1')) -TargetRtlDirectory $TargetRtlDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Rollback failed.' }
} catch { Write-Error $_; exit 1 }
