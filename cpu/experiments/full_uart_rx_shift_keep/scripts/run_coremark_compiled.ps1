param(
    [Parameter(Mandatory)][string]$ConfigurationManifest,
    [Parameter(Mandatory)][string]$FirmwareManifest,
    [ValidateRange(1,1000000000000)][long]$MaxCycles = 50000000,
    [switch]$AllowShort
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $paths = @([System.IO.Path]::Combine($root, 'scripts', 'run_coremark_compiled.py'), $ConfigurationManifest, $FirmwareManifest)
    $linuxPaths = @()
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing input file: $path" }
        $resolved = (Resolve-Path -LiteralPath $path).Path
        $linuxPath = & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $resolved
        if ($LASTEXITCODE) { throw 'WSL path conversion failed.' }
        $linuxPaths += $linuxPath.Trim()
    }
    $arguments = @($linuxPaths[0], '--configuration', $linuxPaths[1], '--firmware-manifest', $linuxPaths[2], '--max-cycles', [string]$MaxCycles)
    if ($AllowShort) { $arguments += '--allow-short' }
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 @arguments
    if ($LASTEXITCODE) { throw 'Compiled CoreMark simulation failed; inspect the printed build directory.' }
} catch {
    Write-Error $_
    exit 1
}
