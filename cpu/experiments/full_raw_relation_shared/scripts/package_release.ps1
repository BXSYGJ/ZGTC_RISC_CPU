param([ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$Label = 'engineering-snapshot')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..'))
    $destination = [System.IO.Path]::Combine($project, 'cpu', 'build', 'deliverables')
    [void](New-Item -ItemType Directory -Path $destination -Force)
    $name = $Label + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8) + '.zip'
    $archive = [System.IO.Path]::Combine($destination, $name)
    $paths = @($project, ([System.IO.Path]::Combine($PSScriptRoot, 'package_release.py')), $archive)
    $linuxPaths = @(foreach ($path in $paths) {
        $converted = (& wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/wslpath -a $path).Trim()
        if ($LASTEXITCODE) { throw 'WSL path conversion failed.' }
        $converted
    })
    & wsl.exe --distribution Ubuntu-22.04 --exec /usr/bin/python3 $linuxPaths[1] --project $linuxPaths[0] --output $linuxPaths[2]
    if ($LASTEXITCODE) { throw 'Package creation or integrity verification failed.' }
    Write-Output "Package: $archive"
    Write-Output 'This is a verified engineering snapshot, not a claim of complete contest acceptance.'
} catch {
    Write-Error $_
    exit 1
}
