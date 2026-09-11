[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
$firmwareSnapshot = $null
try {
    $runner = [System.IO.Path]::Combine($PSScriptRoot, 'run_coremark_test.ps1')
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($runner, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $guards = @{}
    foreach ($message in @('CoreMark build manifest does not match', 'CoreMark firmware changed after build')) {
        $matches = @($ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.IfStatementAst] -and $node.Extent.Text.Contains($message) }, $true))
        if ($matches.Count -ne 1) { throw "Expected one actual runner guard: $message" }
        $guards[$message] = [scriptblock]::Create($matches[0].Extent.Text)
    }
    $manifestGuard = $guards['CoreMark build manifest does not match']
    $imageGuard = $guards['CoreMark firmware changed after build']
    $Iterations = 10
    $ClockHz = 120000000
    $ConsoleDelayCycles = 0
    $ValidationRun = $false
    $EnableM = 1
    $Optimization = 'O3'
    $UnrollLoops = $true
    $LinkTimeOptimization = $false
    $LinkerRelaxation = $false
    $manifest = [pscustomobject]@{
        Iterations = $Iterations
        ClockHz = $ClockHz
        ConsoleDelayCycles = $ConsoleDelayCycles
        ValidationRun = $ValidationRun
        EnableM = $EnableM
        Optimization = $Optimization
        UnrollLoops = $UnrollLoops
        LinkTimeOptimization = $LinkTimeOptimization
        LinkerRelaxation = $LinkerRelaxation
        HexSha256 = ''
    }
    $script:checks = 0
    function Test-Rejection {
        param([scriptblock]$Guard, [string]$Expected)
        $rejected = $false
        try { & $Guard } catch {
            if (-not $_.Exception.Message.Contains($Expected)) { throw }
            $rejected = $true
        }
        if (-not $rejected) { throw "Runner guard accepted invalid input: $Expected" }
        $script:checks++
    }
    & $manifestGuard
    $script:checks++
    foreach ($change in @(
        @{ Name = 'Iterations'; Value = 1 },
        @{ Name = 'ClockHz'; Value = 27000000 },
        @{ Name = 'ConsoleDelayCycles'; Value = 1 },
        @{ Name = 'ValidationRun'; Value = $true },
        @{ Name = 'EnableM'; Value = 0 },
        @{ Name = 'Optimization'; Value = 'O2' },
        @{ Name = 'UnrollLoops'; Value = $false },
        @{ Name = 'LinkTimeOptimization'; Value = $true },
        @{ Name = 'LinkerRelaxation'; Value = $true }
    )) {
        $original = $manifest.($change.Name)
        $manifest.($change.Name) = $change.Value
        Test-Rejection $manifestGuard 'CoreMark build manifest does not match'
        $manifest.($change.Name) = $original
    }
    $ValidationRun = $true
    $LinkTimeOptimization = $true
    $manifest.ValidationRun = $ValidationRun
    $manifest.LinkTimeOptimization = $LinkTimeOptimization
    & $manifestGuard
    $script:checks++
    $firmwareSnapshot = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), ('zgtc-coremark-contract-' + [guid]::NewGuid().ToString('N') + '.hex'))
    [System.IO.File]::WriteAllBytes($firmwareSnapshot, [byte[]]@(1, 2, 3, 4))
    $manifest.HexSha256 = (Get-FileHash -LiteralPath $firmwareSnapshot -Algorithm SHA256).Hash
    & $imageGuard
    $script:checks++
    [System.IO.File]::WriteAllBytes($firmwareSnapshot, [byte[]]@(1, 2, 3, 5))
    Test-Rejection $imageGuard 'CoreMark firmware changed after build'
    $manifest.HexSha256 = ''
    Test-Rejection $imageGuard 'CoreMark firmware changed after build'
    Write-Output "PASS CoreMark runner contract checks=$script:checks"
} catch {
    Write-Error $_
    exit 1
} finally {
    if ($firmwareSnapshot -and (Test-Path -LiteralPath $firmwareSnapshot -PathType Leaf)) {
        Remove-Item -LiteralPath $firmwareSnapshot -Force
    }
}
