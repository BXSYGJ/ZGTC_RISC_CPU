[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    function Test-CachedArguments {
        param([Parameter(Mandatory)][string]$Source)
        $tokens=$null; $errors=$null
        $tree=[System.Management.Automation.Language.Parser]::ParseInput($Source,[ref]$tokens,[ref]$errors)
        if ($errors.Count) { throw "Contract source did not parse." }
        $assignments=@($tree.FindAll({ param($node) $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and $node.Left.VariablePath.UserPath -in @('fastData','fastWrite') },$true))
        foreach ($name in @('fastData','fastWrite')) {
            if (@($assignments | Where-Object { $_.Left.VariablePath.UserPath -eq $name }).Count -ne 1) { throw "Expected exactly one assignment: $name" }
        }
        $commands=@($tree.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'wsl.exe' -and $node.Extent.Text.Contains('/usr/bin/iverilog') },$true))
        if ($commands.Count -ne 1) { throw "Expected one cached compilation command." }
        function wsl.exe {

            $script:CapturedCachedArguments=$args
        }
        $linuxProject='/tmp/cached-contract'; $runName='contract'; $sources=@('source.sv')
        $overlapData=1; $BtbIndexBits=8; $earlyData=1; $overlap=1; $sets=6
        $predictor=1; $enableCache=1; $loadBubble=0; $fastHit=1
        $checks=0
        foreach ($FastDCacheRead in @($false,$true)) {
            foreach ($FastDCacheWrite in @($false,$true)) {
                foreach ($ICacheSetBits in @(0,8)) {
                    foreach ($assignment in $assignments) { . ([scriptblock]::Create($assignment.Extent.Text)) }
                    $script:CapturedCachedArguments=@()
                    & ([scriptblock]::Create($commands[0].Extent.Text))
                    foreach ($expected in @("-Pcached_core_tb.FAST_DCACHE_READ=$([int]$FastDCacheRead)","-Pcached_core_tb.FAST_DCACHE_WRITE=$([int]$FastDCacheWrite)","-Pcached_core_tb.ICACHE_SET_BITS=$ICacheSetBits","-Pcached_core_tb.CACHE_SETS=$sets")) {
                        if ($script:CapturedCachedArguments -notcontains $expected) { throw "Missing actual compiler argument: $expected" }
                    }
                    $checks++
                }
            }
        }
        return $checks
    }
    $source=[IO.File]::ReadAllText([IO.Path]::Combine($PSScriptRoot,'run_cached_tests.ps1'))
    $checks=Test-CachedArguments -Source $source
    $mutants=@(
        $source.Replace('$fastData = if ($FastDCacheRead) { 1 } else { 0 }','$fastData = if ($FastDCacheWrite) { 1 } else { 0 }'),
        $source.Replace('$fastWrite = if ($FastDCacheWrite) { 1 } else { 0 }',('$fastWrite = if ($FastDCacheWrite) { 1 } else { 0 }'+"`n"+'    $fastData = if ($FastDCacheWrite) { 1 } else { 0 }')),
        $source.Replace('-Pcached_core_tb.FAST_DCACHE_READ=$fastData','-Pcached_core_tb.FAST_DCACHE_READ=$fastWrite'),
        $source.Replace('"-Pcached_core_tb.ICACHE_SET_BITS=$ICacheSetBits" ','')
    )
    foreach ($mutant in $mutants) {
        if ($mutant -ceq $source) { throw "Mutation did not match the actual runner." }
        $rejected=$false
        try { $null=Test-CachedArguments -Source $mutant } catch {
            if ($_.Exception.Message -notmatch '^(Missing actual compiler argument:|Expected exactly one assignment:)') { throw }
            $rejected=$true
        }
        if (-not $rejected) { throw "Broken cached runner was accepted." }
        $checks++
    }
    Write-Output "PASS cached runner contract checks=$checks"
} catch {
    Write-Error $_
    exit 1
}
