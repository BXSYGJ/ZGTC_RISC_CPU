param(
    [ValidateSet('Baseline', 'Modified', 'Rollback')]
    [string]$Mode = 'Modified'
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
try {
    $root = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..', '..', '..'))
    $rtl = [System.IO.Path]::Combine($root, 'src', 'ddr3')
    $build = [System.IO.Path]::Combine($root, 'build', 'pacerv_shared_system', 'ddr_bridge')
    New-Item -ItemType Directory -Path $build -Force | Out-Null
    $iverilog = (Get-Command iverilog -ErrorAction Stop).Source
    $vvp = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($iverilog), 'vvp.exe')
    $results = [System.Collections.Generic.List[object]]::new()
    $selectedRtl = $rtl
    if ($Mode -eq 'Rollback') {
        $selectedRtl = [System.IO.Path]::Combine($build, 'rollback_copy')
        New-Item -ItemType Directory -Path $selectedRtl -Force | Out-Null
        foreach ($name in @('ddr3_ctrl_axi.v', 'ddr3_arbiter.v', 'pace_cpu_ddr_bridge.v', 'ddr3_m3_share.v')) {
            Copy-Item -LiteralPath ([System.IO.Path]::Combine($rtl, $name)) -Destination ([System.IO.Path]::Combine($selectedRtl, $name))
        }
        & ([System.IO.Path]::Combine($PSScriptRoot, 'ROLLBACK.ps1')) -TargetRtlDirectory $selectedRtl
        if ($LASTEXITCODE -ne 0) { throw 'Rollback script failed.' }
    }
    $ctrl = [System.IO.Path]::Combine($selectedRtl, 'ddr3_ctrl_axi.v')
    $arb = [System.IO.Path]::Combine($selectedRtl, 'ddr3_arbiter.v')
    if ($Mode -eq 'Baseline') {
        $ctrl = [System.IO.Path]::Combine($PSScriptRoot, 'ddr3_ctrl_axi.v.original')
        $arb = [System.IO.Path]::Combine($PSScriptRoot, 'ddr3_arbiter.v.original')
    }
    $cases = @(
        [pscustomobject]@{ Name = 'legacy'; Top = 'tb_ddr3_byteaddr'; Pass = 'RESULT: PASS'; Sources = @(
            [System.IO.Path]::Combine($PSScriptRoot, 'tb_pacerv_legacy_byteaddr.sv'), $ctrl, $arb,
            [System.IO.Path]::Combine($root, 'sim', 'ddr3_axi_model.sv')) }
    )
    if ($Mode -eq 'Modified') {
        $cases += [pscustomobject]@{ Name = 'shared_ddr'; Top = 'tb_pacerv_shared_ddr'; Pass = 'PACERV_SHARED_DDR PASS'; Sources = @(
            [System.IO.Path]::Combine($PSScriptRoot, 'tb_pacerv_shared_ddr.sv'),
            [System.IO.Path]::Combine($rtl, 'pace_cpu_ddr_bridge.v'),
            [System.IO.Path]::Combine($rtl, 'ddr3_m3_share.v'), $ctrl, $arb) }
        $cases += [pscustomobject]@{ Name = 'm3_share'; Top = 'tb_pacerv_m3_share'; Pass = 'PACERV_M3_SHARE PASS'; Sources = @(
            [System.IO.Path]::Combine($PSScriptRoot, 'tb_pacerv_m3_share.sv'),
            [System.IO.Path]::Combine($rtl, 'ddr3_m3_share.v')) }
        $cases += [pscustomobject]@{ Name = 'local_timeout'; Top = 'tb_pacerv_local_timeout'; Pass = 'PACERV_LOCAL_TIMEOUT PASS'; Sources = @(
            [System.IO.Path]::Combine($PSScriptRoot, 'tb_pacerv_local_timeout.sv'),
            [System.IO.Path]::Combine($rtl, 'pace_cpu_ddr_bridge.v'),
            [System.IO.Path]::Combine($rtl, 'ddr3_m3_share.v')) }
        $cases += [pscustomobject]@{ Name = 'boot_selftest'; Top = 'tb_pacerv_boot_selftest'; Pass = 'PACERV_BOOT_SELFTEST PASS'; Sources = @(
            [System.IO.Path]::Combine($PSScriptRoot, 'tb_pacerv_boot_selftest.sv'),
            [System.IO.Path]::Combine($root, 'src', 'ctrl', 'self_test.v'),
            [System.IO.Path]::Combine($rtl, 'ddr3_m3_share.v'), $ctrl, $arb,
            [System.IO.Path]::Combine($root, 'sim', 'ddr3_axi_model.sv')) }
    }
    foreach ($case in $cases) {
        $outputFile = [System.IO.Path]::Combine($build, ($Mode + '_' + $case.Name + '.vvp'))
        $compileArgs = @('-g2012', '-s', $case.Top, '-o', $outputFile) + $case.Sources
        $compileOutput = @(& $iverilog @compileArgs 2>&1)
        $compileExit = $LASTEXITCODE
        if ($compileExit -ne 0) { throw ('Compile failed: ' + ($compileOutput -join [Environment]::NewLine)) }
        $runOutput = @(& $vvp $outputFile 2>&1)
        $runExit = $LASTEXITCODE
        $literalOutput = ($runOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
        if ($runExit -ne 0 -or !$literalOutput.Contains($case.Pass)) { throw ('Test failed: ' + $literalOutput) }
        $results.Add([pscustomobject]@{
            Case = $case.Name; Compiler = $iverilog; CompileArguments = $compileArgs;
            CompileOutput = ($compileOutput -join [Environment]::NewLine); CompileExit = $compileExit;
            RunCommand = @($vvp, $outputFile); Output = $literalOutput; RunExit = $runExit
        })
        Write-Output $literalOutput
    }
    $resultPath = [System.IO.Path]::Combine($PSScriptRoot, ($Mode.ToUpperInvariant() + '_RESULTS.json'))
    [System.IO.File]::WriteAllText($resultPath, (ConvertTo-Json -InputObject $results.ToArray() -Depth 8), [System.Text.UTF8Encoding]::new($true))
    Write-Output ($Mode.ToUpperInvariant() + ' PASS cases=' + $cases.Count)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
