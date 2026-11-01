#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Original_155250','H3_Base_145125','H3_Retained_145125')]
    [string[]] $Release = @('Original_155250','H3_Base_145125','H3_Retained_145125'),
    [ValidateRange(2000000,10000000)]
    [long] $Cycles = 2000000
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $script = [System.IO.Path]::Combine($PSScriptRoot,'qualify_extraction.py')
    $arguments = @($script,'--cycles',$Cycles.ToString([Globalization.CultureInfo]::InvariantCulture))
    foreach ($name in $Release) { $arguments += @('--release',$name) }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw ('Extraction miter failed with exit status ' + $LASTEXITCODE) }
} catch {
    Write-Error $_
    exit 1
}
