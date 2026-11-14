#Requires -Version 7.0
# Load the exact eight-class image shipped with the native HDMI release.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('(?i)^COM[1-9][0-9]{0,3}$')]
    [string]$SerialPort,

    [ValidateNotNullOrEmpty()]
    [string]$PythonExe = 'python',

    [string]$ImagePath,
    [string]$UploaderPath,
    [switch]$DryRun
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Set-StrictMode -Version Latest

try {
    if ([string]::IsNullOrWhiteSpace($ImagePath)) {
        $ImagePath = [System.IO.Path]::Combine($PSScriptRoot, 'runtime', 'weights_image.bin')
    }
    if ([string]::IsNullOrWhiteSpace($UploaderPath)) {
        $UploaderPath = [System.IO.Path]::Combine($PSScriptRoot, 'runtime', 'weight_upload.py')
    }
    foreach ($inputPath in @($ImagePath, $UploaderPath)) {
        if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
            throw "Required runtime file is missing: $inputPath"
        }
    }
    $ImagePath = (Resolve-Path -LiteralPath $ImagePath).ProviderPath
    $UploaderPath = (Resolve-Path -LiteralPath $UploaderPath).ProviderPath
    $expectedSha256 = '19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a'
    $actualSha256 = (Get-FileHash -LiteralPath $ImagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $imageBytes = (Get-Item -LiteralPath $ImagePath).Length
    if ($imageBytes -ne 691040 -or $actualSha256 -ne $expectedSha256) {
        throw "Eight-class weight image hash or length differs: $ImagePath"
    }
    $pythonCommand = Get-Command -Name $PythonExe -CommandType Application -ErrorAction Stop |
        Select-Object -First 1
    $uploaderArguments = @('-X', 'utf8', $UploaderPath, '--port', $SerialPort.ToUpperInvariant(), '--image', $ImagePath)
    $mode = 'upload'
    if ($DryRun) {
        $uploaderArguments += '--dry-run'
        $mode = 'dry-run'
    }
    & $pythonCommand.Source @uploaderArguments
    $uploaderExitStatus = $LASTEXITCODE
    if ($uploaderExitStatus -ne 0) {
        throw "Weight uploader exited with status $uploaderExitStatus"
    }
    Write-Output "WEIGHT_LAUNCHER_PASS mode=$mode bytes=$imageBytes sha256=$actualSha256 uploader_exit=0"
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
