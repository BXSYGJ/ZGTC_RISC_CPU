[CmdletBinding()]
param(
    [ValidateSet('inspect','run')][string]$Action = 'inspect',
    [string]$Bitstream = '', [string]$OutputDirectory = '',
    [ValidateRange(1,1800)][int]$Seconds = 90,
    [ValidateRange(1200,2000000)][int]$Baud = 115200,
    [string]$AccountFile = ''
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
try {
    $env:PYTHONIOENCODING = 'utf-8'
    $arguments = @([System.IO.Path]::Combine($PSScriptRoot, 'remote_capture.py'), $Action, '--seconds', $Seconds, '--baud', $Baud)
    if ($Action -eq 'run') {
        if (-not $Bitstream -or -not $OutputDirectory) { throw 'run requires Bitstream and OutputDirectory.' }
        $arguments += @('--bitstream', [System.IO.Path]::GetFullPath($Bitstream), '--output', [System.IO.Path]::GetFullPath($OutputDirectory))
    }
    if ($AccountFile) { $arguments += @('--account', [System.IO.Path]::GetFullPath($AccountFile)) }
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "Remote capture failed: $LASTEXITCODE" }
} catch {
    Write-Error $_
    exit 1
}
