#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Workspace
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $taskRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $allowedRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($taskRoot, 'build', 'rtos')) + [System.IO.Path]::DirectorySeparatorChar
    $resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path
    if (-not $resolvedWorkspace.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Rollback accepts an isolated workspace under instrec_fpga/build/rtos only.'
    }
    $baselineRoot = [System.IO.Path]::Combine($PSScriptRoot, 'baseline125')
    $manifestPath = [System.IO.Path]::Combine($PSScriptRoot, 'BASELINE.json')
    $manifest = [System.IO.File]::ReadAllText($manifestPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
    foreach ($entry in $manifest.files) {
        $relative = [string]$entry.path
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Split('/') -contains '..') {
            throw 'Unexpected baseline manifest path.'
        }
        $source = [System.IO.Path]::Combine($baselineRoot, $relative)
        $destination = [System.IO.Path]::Combine($resolvedWorkspace, $relative)
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
            throw ('Baseline hash mismatch: ' + $relative)
        }
        [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destination)) | Out-Null
        [System.IO.File]::WriteAllBytes($destination, [System.IO.File]::ReadAllBytes($source))
    }
    $addedTimer = [System.IO.Path]::Combine($resolvedWorkspace, 'src', 'cpu', 'machine_timer.v')
    if (Test-Path -LiteralPath $addedTimer) {
        Remove-Item -LiteralPath $addedTimer
    }
    foreach ($entry in $manifest.files) {
        $destination = [System.IO.Path]::Combine($resolvedWorkspace, [string]$entry.path)
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {
            throw ('Restored hash mismatch: ' + $entry.path)
        }
    }
    Write-Output ('ROLLBACK_RESTORED files=' + $manifest.source_count + ' clock_hz=125000000 timer_removed=1')
} catch {
    Write-Error $_
    exit 1
}
