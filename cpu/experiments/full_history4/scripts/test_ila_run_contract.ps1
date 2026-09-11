param([ValidateSet('Target120', 'Target132Carry', 'Target132Kept')][string]$Profile = 'Target120')
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $project = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
    $root = [System.IO.Path]::Combine($project, 'build', 'ila-contract', [guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $root -Force)
    $runner = [System.IO.Path]::Combine($PSScriptRoot, 'run_ila_pds.ps1')
    $shell = [System.IO.Path]::Combine($PSHOME, 'pwsh.exe')
    $clockHz = if ($Profile -in @('Target132Carry', 'Target132Kept')) { 132000000 } else { 120000000 }
    $sourceLockName = switch ($Profile) {
        'Target132Carry' { 'ila_target132_carry_sources.json' }
        'Target132Kept' { 'ila_target132_kept_sources.json' }
        default { 'ila_target120_sources.json' }
    }
    $required = [ordered]@{ Device='PG2L200H-6FBB676'; ClockHz=$clockHz; CacheEnabled=1; Predictor=1; UartProfile='RemoteLab'; UartBaud=115200; EnableM=1; FetchOverlap=1; FastDCacheRead=1; FastDCacheWrite=1; ICacheSetBits=8; CacheSetBits=6; EarlyDRequest=1; BtbIndexBits=8; DataOverlap=1; FastICacheHit=1; LoadUseBubble=0; TimingConstraintsMet=$true }
    $checks = 0
    foreach ($name in @($required.Keys) + @('EmptySnapshot','WrongRevision')) {
        $manifest = [ordered]@{}
        foreach ($key in $required.Keys) { $manifest[$key] = $required[$key] }
        $manifest['SourceSnapshot'] = @{ Files=(Get-Content -LiteralPath ([System.IO.Path]::Combine($PSScriptRoot, $sourceLockName)) -Raw | ConvertFrom-Json -AsHashtable) }
        if ($name -eq 'EmptySnapshot') {
            $manifest.SourceSnapshot.Files = @{}
            $expected = "$Profile source map is incomplete or unsupported"
        } elseif ($name -eq 'WrongRevision') {
            $manifest.SourceSnapshot.Files['rtl/rv32_core.sv'] = '0' * 64
            $expected = "$Profile source revision requires ILA remapping"
        } else {
            $manifest[$name] = if ($manifest[$name] -is [bool]) { $false } elseif ($manifest[$name] -is [string]) { 'invalid' } else { -1 }
            $expected = "$Profile ILA configuration mismatch: $name"
        }
        $directory = [System.IO.Path]::Combine($root, $name)
        [void](New-Item -ItemType Directory -Path $directory)
        $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([System.IO.Path]::Combine($directory, 'manifest.json')) -Encoding utf8BOM
        $output = & $shell -NoProfile -File $runner -Profile $Profile -SourceBuild $directory 2>&1
        $exitCode = $LASTEXITCODE
        $text = ($output | Out-String)
        if ($exitCode -eq 0 -or -not $text.Contains($expected) -or $text.Contains('PDS ILA PID') -or $text.Contains('ILA net validation PID')) { throw "ILA preflight rejection failed: $name $text" }
        $checks++
    }
    Write-Output "PASS ILA $Profile preflight checks=$checks"
    exit 0
} catch {
    Write-Error $_
    exit 1
}
