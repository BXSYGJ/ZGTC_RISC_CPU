[CmdletBinding()]
param([string]$PackageRoot = [System.IO.Path]::Combine($PSScriptRoot,'..','..'))
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.UTF8Encoding]::new($true)
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath($PackageRoot)
    $manifest = [System.IO.Path]::Combine($root,'FILE_MANIFEST.csv')
    if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) {throw 'Extract the complete archive before verification'}
    $count = 0
    foreach ($row in Import-Csv -LiteralPath $manifest -Encoding utf8) {
        $path = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root,$row.ArchivePath))
        if (-not $path.StartsWith($root+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) {throw 'Manifest path leaves package root'}
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {throw "Missing file: $($row.ArchivePath)"}
        if ((Get-Item -LiteralPath $path).Length -ne [long]$row.Bytes -or (Get-FileHash -LiteralPath $path).Hash -ne $row.SHA256) {throw "Changed file: $($row.ArchivePath)"}
        $count++
    }
    Write-Output "Verified $count files against SHA-256 manifest."
    exit 0
} catch {Write-Error $_;exit 1}
