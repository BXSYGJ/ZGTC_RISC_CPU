param(
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$BuildDirectory,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$TargetDirectory
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $build = [System.IO.Path]::GetFullPath($BuildDirectory)
    $target = [System.IO.Path]::GetFullPath($TargetDirectory)
    $frozen = [System.IO.Path]::Combine($build, 'frozen_inputs')
    $manifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($build, 'source-hashes.json')) -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    if (-not $target.StartsWith($build + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Rollback target must be inside its build directory.' }
    if ($target -eq $frozen -or $target.StartsWith($frozen + [System.IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Rollback target must be a separate copy.' }
    foreach ($relative in $manifest.Keys) {
        $source = [System.IO.Path]::Combine($frozen, $relative)
        $destination = [System.IO.Path]::Combine($target, $relative)
        if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $manifest[$relative]) { throw "Frozen input hash changed: $relative" }
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destination))
        Copy-Item -LiteralPath $source -Destination $destination -Force
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $manifest[$relative]) { throw "Rollback mismatch: $relative" }
    }
    Write-Output ('ROLLBACK PASS: restored ' + $manifest.Count + ' frozen input files; original INIT_FILE binding restored; functional RTL and firmware SHA256 match baseline.')
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
