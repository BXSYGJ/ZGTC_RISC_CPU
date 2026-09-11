[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $runner = [System.IO.Path]::Combine($PSScriptRoot, 'run_ila_pds.ps1')
    $parseTokens = $null
    $parseErrors = $null
    $tree = [System.Management.Automation.Language.Parser]::ParseFile($runner, [ref]$parseTokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw 'ILA runner has syntax errors.' }
    $mainTry = @($tree.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.TryStatementAst] })
    if ($mainTry.Count -ne 1) { throw 'ILA runner must have one main try block.' }
    $terminal = $mainTry[0].Body.Statements[-1]
    if ($terminal -isnot [System.Management.Automation.Language.ExitStatementAst] -or $terminal.Extent.Text -cne 'exit 0') { throw 'ILA successful path must explicitly exit zero.' }
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', 'build', 'ila-exit-contract', [guid]::NewGuid().ToString('N')))
    [void](New-Item -ItemType Directory -Path $root)
    $probe = [System.IO.Path]::Combine($root, 'probe.ps1')
    $harness = [System.IO.Path]::Combine($root, 'harness.ps1')
    $shell = [System.IO.Path]::Combine($PSHOME, 'pwsh.exe')
    $utf8 = [System.Text.UTF8Encoding]::new($true)
    $checks = 0
    foreach ($explicitExit in @($true, $false)) {
        $probeLines = @('[Console]::OutputEncoding = [System.Text.Encoding]::UTF8', '$ErrorActionPreference = ''Stop''', 'try {', 'Write-Output ''synthetic successful tail''')
        if ($explicitExit) { $probeLines += $terminal.Extent.Text }
        $probeLines += @('} catch { Write-Error $_; exit 1 }')
        [System.IO.File]::WriteAllLines($probe, $probeLines, $utf8)
        foreach ($initial in @('missing', 'stale')) {
            $initialCommand = if ($initial -eq 'missing') { 'Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue' } else { '$global:LASTEXITCODE = 23' }
            $harnessLines = @('[Console]::OutputEncoding = [System.Text.Encoding]::UTF8', '$ErrorActionPreference = ''Stop''', 'try {', $initialCommand,
                '& ([System.IO.Path]::Combine($PSScriptRoot, ''probe.ps1''))',
                'if ($LASTEXITCODE -ne 0) { throw ''FAIL caller observed missing or stale exit code'' }',
                'Write-Output ''PASS caller observed explicit zero''', 'exit 0', '} catch { Write-Error $_; exit 1 }')
            [System.IO.File]::WriteAllLines($harness, $harnessLines, $utf8)
            $output = & $shell -NoProfile -File $harness 2>&1
            $exitCode = $LASTEXITCODE
            $text = $output | Out-String
            $expected = if ($explicitExit) { 'PASS caller observed explicit zero' } else { 'FAIL caller observed missing or stale exit code' }
            if (($explicitExit -and $exitCode -ne 0) -or (-not $explicitExit -and $exitCode -eq 0) -or -not $text.Contains($expected)) { throw "ILA exit contract failed: explicit=$explicitExit initial=$initial $text" }
            $text | Out-File -LiteralPath ([System.IO.Path]::Combine($root, "explicit-$explicitExit-$initial.log")) -Encoding utf8BOM
            $checks++
        }
    }
    Write-Output "PASS ILA successful exit checks=$checks; synthetic tail only, no vendor process."
    exit 0
} catch {
    Write-Error $_
    exit 1
}
