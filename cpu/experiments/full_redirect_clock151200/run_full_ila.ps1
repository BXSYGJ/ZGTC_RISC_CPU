param([ValidatePattern('^[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$')][string]$SourceRun = '20260910-233603-e3b63565', [ValidatePattern('^[a-zA-Z0-9-]+$')][string]$RunName = '20260910-redirect-clock151200-seed2', [ValidateRange(1,32)][int]$PlacementSeed = 2, [switch]$ValidationRun)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $source = [IO.Path]::Combine($PSScriptRoot, 'build', 'pds', $SourceRun)
    $build = [IO.Path]::Combine($PSScriptRoot, 'build', 'ila', $RunName)
    if (Test-Path -LiteralPath $build) { throw 'ILA run already exists; inspect its actual process and outputs instead of restarting.' }
    $sourceLog = Get-Content -LiteralPath ([IO.Path]::Combine($source, 'run.log')) -Raw -Encoding utf8
    if (-not $sourceLog.Contains('Executing : synthesize -ads -selected_syn_tool_opt 2 successfully.')) { throw 'Synthesis completion is not proven.' }
    [string[]]$validationArguments = @()
    if ($ValidationRun) { $validationArguments = @('--validation') }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_binding.py')) --source $source @validationArguments
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark hardware binding failed.' }
    $env:PANGO_LICENSE_FILE = [Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE', 'User')
    if ([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)) { throw 'PDS license is not configured.' }
    $pdsRoot = [IO.Path]::Combine('D:/', 'PDS_2022.2-SP6.4', 'bin')
    [void](New-Item -ItemType Directory -Path $build)
    $copies = @{
        'source.adf' = [IO.Path]::Combine('synthesize', 'pds_soc_top_syn.adf')
        'netlist.v' = [IO.Path]::Combine('synthesize', 'pds_soc_top_syn.vm')
        'firmware.hex' = 'firmware.hex'
        'source-snapshot.json' = 'source-snapshot.json'
        'board.fdc' = [IO.Path]::Combine('source', 'constraints', 'board.fdc')
        'uart_remotelab.fdc' = [IO.Path]::Combine('source', 'constraints', 'uart_remotelab.fdc')
    }
    foreach ($name in $copies.Keys) { Copy-Item -LiteralPath ([IO.Path]::Combine($source, $copies[$name])) -Destination ([IO.Path]::Combine($build, $name)) }
    $template = [IO.Path]::Combine($PSScriptRoot, '..', 'full_control_commit', 'build', 'ila', '20260910-control-commit-seed2', 'cpu-remapped.fic')
    $adf = [IO.Path]::Combine($build, 'source.adf').Replace([IO.Path]::DirectorySeparatorChar, '/')
    $fic = [IO.Path]::Combine($build, 'cpu-remapped.fic').Replace([IO.Path]::DirectorySeparatorChar, '/')
    foreach ($value in @($build, $adf, $fic)) { if ($value -match '[{}"$;\r\n]') { throw 'Unsafe Tcl path.' } }
    $configuration = [regex]::Replace([IO.File]::ReadAllText($template), '(?m)^Project.device.designInputFile=[^\r\n]+', ('Project.device.designInputFile=' + $adf))
    $configuration = $configuration.Replace('board/soc/unused_pipeline_valid[0]', 'board/soc/core/pipeline_valid[0]').Replace('board/soc/unused_pipeline_valid[1]', 'board/soc/core/pipeline_valid[1]').Replace('board/soc/unused_pipeline_valid[3]', 'board/soc/core/pipeline_valid[3]')
    [IO.File]::WriteAllText($fic, $configuration, [Text.UTF8Encoding]::new($false))
    $verify = [IO.Path]::Combine($build, 'verify-remapped.tcl')
    [IO.File]::WriteAllLines($verify, @("ins_open {$fic}", 'ins_core_info -core 0', 'ins_core_info -core 0 -trig 0', 'ins_save', 'exit'), [Text.UTF8Encoding]::new($false))
    $verifyProcess = Start-Process -FilePath ([IO.Path]::Combine($pdsRoot, 'cdt_ins.exe')) -ArgumentList @('-device', 'PG2L200H', '-package', 'FBB676', '-speedgrade', '-6', '-file', ('"' + $verify.Replace([IO.Path]::DirectorySeparatorChar, '/') + '"')) -WorkingDirectory $build -PassThru -WindowStyle Hidden -RedirectStandardOutput ([IO.Path]::Combine($build, 'verify-remapped.stdout.txt')) -RedirectStandardError ([IO.Path]::Combine($build, 'verify-remapped.stderr.txt'))
    Write-Output ('CoreMark Inserter PID: ' + $verifyProcess.Id)
    $verifyProcess.WaitForExit()
    if ($verifyProcess.ExitCode -ne 0) { throw 'CoreMark Inserter failed.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'audit_ila_mapping.py')) --stage $build --source $source @validationArguments
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark ILA mapping failed.' }
    $lines = @(
        ('add_design {' + [IO.Path]::Combine($build, 'netlist.v').Replace([IO.Path]::DirectorySeparatorChar, '/') + '}'),
        ('add_constraint {' + [IO.Path]::Combine($build, 'board.fdc').Replace([IO.Path]::DirectorySeparatorChar, '/') + '}'),
        ('add_constraint {' + [IO.Path]::Combine($build, 'uart_remotelab.fdc').Replace([IO.Path]::DirectorySeparatorChar, '/') + '}'),
        ('add_fic {' + $fic + '}'),
        'set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676',
        'compile -system_verilog -top_module pds_soc_top',
        ('dev_map -input_db_file {' + $adf + '}'),
        ('pnr -gplace_seed ' + $PlacementSeed), 'report_timing', 'gen_bit_stream'
    )
    $script = [IO.Path]::Combine($build, 'build.tcl')
    [IO.File]::WriteAllLines($script, $lines, [Text.UTF8Encoding]::new($false))
    $inputs = [ordered]@{}
    foreach ($name in @('source.adf', 'netlist.v', 'firmware.hex', 'cpu-remapped.fic', 'board.fdc', 'uart_remotelab.fdc', 'build.tcl', 'mapping-audit.json')) { $inputs[$name] = (Get-FileHash -LiteralPath ([IO.Path]::Combine($build, $name)) -Algorithm SHA256).Hash }
    $invocation = [ordered]@{ Schema = 1; StartedUtc = [datetime]::UtcNow.ToString('o'); WorkingDirectory = $build; PlacementSeed = $PlacementSeed; Inputs = $inputs; ExitCode = $null }
    $receipt = [IO.Path]::Combine($build, 'invocation.json')
    $invocation | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receipt -Encoding utf8BOM
    $process = Start-Process -FilePath ([IO.Path]::Combine($pdsRoot, 'pds_shell.exe')) -ArgumentList @('-file', ('"' + $script + '"'), '-work_dir', ('"' + $build + '"'), '-project_name', 'cpu_ila') -WorkingDirectory $build -PassThru -WindowStyle Hidden -RedirectStandardOutput ([IO.Path]::Combine($build, 'pds.stdout.log')) -RedirectStandardError ([IO.Path]::Combine($build, 'pds.stderr.log'))
    $invocation['Pid'] = $process.Id
    $invocation | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receipt -Encoding utf8BOM
    Write-Output ('CoreMark full ILA PID: ' + $process.Id + '; directory: ' + $build)
    $process.WaitForExit()
    $invocation['ExitCode'] = $process.ExitCode
    $invocation['FinishedUtc'] = [datetime]::UtcNow.ToString('o')
    $invocation | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receipt -Encoding utf8BOM
    if ($process.ExitCode -ne 0) { throw 'CoreMark full ILA implementation failed.' }
    & python ([IO.Path]::Combine($PSScriptRoot, 'qualify_full_ila.py')) --stage $build --source $source --placement-seed $PlacementSeed @validationArguments
    if ($LASTEXITCODE -ne 0) { throw 'CoreMark full ILA qualification failed.' }
} catch {
    Write-Error $_
    exit 1
}
