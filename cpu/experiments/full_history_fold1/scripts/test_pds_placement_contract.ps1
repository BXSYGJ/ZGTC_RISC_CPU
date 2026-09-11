[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$buildRoot = $null
try {
    $runner = [System.IO.Path]::Combine($PSScriptRoot, 'run_pds.ps1')
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $text = $ast.Extent.Text
    $start = $text.IndexOf('    $placement = [ordered]@{')
    $end = $text.IndexOf('    $uartConstraint =', $start)
    if ($start -lt 0 -or $end -le $start) { throw 'Missing actual placement configuration block.' }
    $configure = [scriptblock]::Create($ast.ParamBlock.Extent.Text + [Environment]::NewLine + $text.Substring($start, $end - $start) + [Environment]::NewLine + '[pscustomobject]@{ Placement = $placement; Tcl = $template }')
    $originalTemplate = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($PSScriptRoot, 'build_pds.tcl'))
    $buildRoot = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), ('zgtc-placement-' + [guid]::NewGuid().ToString('N')))
    [void](New-Item -ItemType Directory -Path $buildRoot)
    $checks = 0
    foreach ($case in @(
        @{ Arguments = @{}; Seed = $null; Command = 'pnr' },
        @{ Arguments = @{ PlacementSeed = 0 }; Seed = 0; Command = 'pnr -gplace_seed 0' },
        @{ Arguments = @{ PlacementSeed = 1 }; Seed = 1; Command = 'pnr -gplace_seed 1' },
        @{ Arguments = @{ PlacementSeed = 7 }; Seed = 7; Command = 'pnr -gplace_seed 7' },
        @{ Arguments = @{ PlacementSeed = 2147483647 }; Seed = 2147483647; Command = 'pnr -gplace_seed 2147483647' }
    )) {
        $template = $originalTemplate
        $arguments = $case.Arguments
        $result = & $configure @arguments
        $saved = Get-Content -LiteralPath ([System.IO.Path]::Combine($buildRoot, 'placement-config.json')) -Raw | ConvertFrom-Json
        if ($result.Placement.Seed -ne $case.Seed -or $saved.Seed -ne $case.Seed -or $saved.Command -cne $case.Command) { throw 'Placement metadata differs from requested configuration.' }
        $pnrLines = @($result.Tcl -split '\r?\n' | Where-Object { $_ -match '^pnr(?: |$)' })
        if ($pnrLines.Count -ne 1 -or $pnrLines[0] -cne $case.Command -or $result.Tcl.Contains('__PNR_COMMAND__')) { throw 'Actual Tcl command differs from placement metadata.' }
        if ($result.Tcl -cne $originalTemplate.Replace('__PNR_COMMAND__', $case.Command)) { throw 'Placement changed unrelated Tcl commands.' }
        $checks++
    }
    foreach ($invalid in @(-1, 2147483648, '1; exit', 'abc')) {
        $template = $originalTemplate
        $rejected = $false
        try { & $configure -PlacementSeed $invalid | Out-Null } catch [System.Management.Automation.ParameterBindingException] { $rejected = $true }
        if (-not $rejected) { throw 'Actual runner parameters accepted an invalid seed.' }
        $checks++
    }
    foreach ($invalidTemplate in @($originalTemplate.Replace('__PNR_COMMAND__', 'pnr'), ($originalTemplate + '__PNR_COMMAND__'))) {
        $template = $invalidTemplate
        $rejected = $false
        try { & $configure -PlacementSeed 1 | Out-Null } catch {
            if ($_.Exception.Message -notmatch 'Expected one PDS placement command placeholder') { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw 'Runner accepted a missing or duplicate placement command placeholder.' }
        $checks++
    }
    Write-Output "PASS PDS placement contract checks=$checks"
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($buildRoot -and (Test-Path -LiteralPath $buildRoot -PathType Container)) {
        $configPath = [System.IO.Path]::Combine($buildRoot, 'placement-config.json')
        if (Test-Path -LiteralPath $configPath -PathType Leaf) { Remove-Item -LiteralPath $configPath }
        Remove-Item -LiteralPath $buildRoot
    }
}
