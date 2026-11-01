#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string] $Root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..')),
    [ValidateRange(8, 128)]
    [int] $ZoomLength = 32
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'

try {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw 'The release root directory does not exist.'
    }
    $renderer = [System.IO.Path]::Combine($PSScriptRoot, 'render_ila_waveforms.py')
    $python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    & $python $renderer --all-root $Root --zoom-length $ZoomLength
    if ($LASTEXITCODE -ne 0) {
        throw ('Local RTL waveform rendering failed with exit status ' + $LASTEXITCODE)
    }
} catch {
    Write-Error $_
    exit 1
}
