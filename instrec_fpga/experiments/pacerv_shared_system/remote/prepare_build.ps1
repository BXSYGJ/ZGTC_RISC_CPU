[CmdletBinding()]
param([string]$VendorIp = '', [string]$BuildDirectory = '')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $arguments = @([System.IO.Path]::Combine($PSScriptRoot, 'prepare_build.py'))
    if ($VendorIp) { $arguments += @('--vendor-ip', [System.IO.Path]::GetFullPath($VendorIp)) }
    if ($BuildDirectory) { $arguments += @('--output', [System.IO.Path]::GetFullPath($BuildDirectory)) }
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Build preparation failed: $LASTEXITCODE" }
} catch {
    Write-Error $_
    exit 1
}
