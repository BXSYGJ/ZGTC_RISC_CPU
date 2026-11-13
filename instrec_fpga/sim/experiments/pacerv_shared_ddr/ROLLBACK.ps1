param([Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$TargetRtlDirectory)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $target = [System.IO.Path]::GetFullPath($TargetRtlDirectory)
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..', '..'))
    $prefix = $root + [System.IO.Path]::DirectorySeparatorChar
    if (!$target.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Target must be a task workspace subdirectory.' }
    if (!(Test-Path -LiteralPath $target -PathType Container)) { throw 'Target directory must already exist.' }
    foreach ($name in @('ddr3_ctrl_axi.v', 'ddr3_arbiter.v')) {
        $source = [System.IO.Path]::Combine($PSScriptRoot, ($name + '.original'))
        $destination = [System.IO.Path]::Combine($target, $name)
        Copy-Item -LiteralPath $source -Destination $destination
        if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) { throw ('Restored hash mismatch: ' + $name) }
    }
    foreach ($name in @('pace_cpu_ddr_bridge.v', 'ddr3_m3_share.v')) {
        $newFile = [System.IO.Path]::Combine($target, $name)
        if (Test-Path -LiteralPath $newFile -PathType Leaf) { Remove-Item -LiteralPath $newFile -Force }
    }
    Write-Output 'ROLLBACK HASH PASS restored=2 removed_new=2'
    exit 0
} catch {
    Write-Error $_
    exit 1
}
