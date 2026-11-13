[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })][string]$BaselineDirectory,
    [Parameter(Mandatory)][ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })][string]$TargetDirectory,
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Container })][string]$EvidenceDirectory = $PSScriptRoot
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
try {
    $baselineRoot = [System.IO.Path]::GetFullPath($BaselineDirectory)
    $targetRoot = [System.IO.Path]::GetFullPath($TargetDirectory)
    $marker = [System.IO.Path]::Combine($targetRoot, 'ROLLBACK_TEST_COPY.json')
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'Target must be a marked isolated test copy.' }
    $manifestPath = [System.IO.Path]::Combine($EvidenceDirectory, 'BASELINE_MANIFEST.json')
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    $sourcePrefix = $baselineRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $targetPrefix = $targetRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    foreach ($entry in $manifest.files) {
        $source = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($baselineRoot, [string]$entry.path))
        $target = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($targetRoot, [string]$entry.path))
        if (-not $source.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Source escapes baseline.' }
        if (-not $target.StartsWith($targetPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Target escapes isolated copy.' }
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Baseline hash differs: $($entry.path)" }
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($target)) | Out-Null
        [System.IO.File]::Copy($source, $target, $true)
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $entry.sha256) { throw "Restored hash differs: $($entry.path)" }
    }
    Write-Output "INTEGRATION_ROLLBACK_RESTORED files=$($manifest.files.Count) isolated_copy=1"
} catch {
    Write-Error $_
    exit 1
}
