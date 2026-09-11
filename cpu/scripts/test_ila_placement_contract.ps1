[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $runner = [System.IO.Path]::Combine($PSScriptRoot, 'run_ila_pds.ps1')
    $shell = [System.IO.Path]::Combine($PSHOME, 'pwsh.exe')
    $checks = 0
    foreach ($seed in @('-1', '2147483648', '1;exit')) {
        $output = & $shell -NoProfile -File $runner -SourceBuild $root -Profile Target132Carry -PlacementSeed $seed 2>&1
        $exitCode = $LASTEXITCODE
        $text = $output | Out-String
        if ($exitCode -eq 0 -or -not $text.Contains('PlacementSeed') -or $text.Contains('PDS ILA PID') -or $text.Contains('ILA net validation PID')) { throw "ILA placement argument was not rejected: $seed $text" }
        $checks++
    }
    Write-Output "PASS ILA placement argument checks=$checks"
    exit 0
} catch {
    Write-Error $_
    exit 1
}

