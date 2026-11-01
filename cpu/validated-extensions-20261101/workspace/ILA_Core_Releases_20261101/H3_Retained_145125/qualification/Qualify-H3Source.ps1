param(
    [ValidateSet('H3_Base_145125', 'H3_Retained_145125')][string]$Release = 'H3_Base_145125'
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $workspace = [System.IO.Path]::Combine('D:', 'AAAFPGA')
    $taskRoot = [System.IO.Path]::Combine($workspace, 'ILA_Core_Releases_20261101')
    $sourceRoot = [System.IO.Path]::Combine($workspace, 'Current_Paper_and_Sub7000_Core_Releases_20261012', 'cores', $Release)
    $outputRoot = [System.IO.Path]::Combine($taskRoot, $Release, 'qualification')
    [void][System.IO.Directory]::CreateDirectory($outputRoot)
    $utf8Bom = [System.Text.UTF8Encoding]::new($true)
    function Save-Json([string]$Path, [object]$Value) {
        [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 30), $utf8Bom)
    }
    function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    function Convert-LinuxPath([string]$Path) {
        $full = [System.IO.Path]::GetFullPath($Path)
        if ($full -notmatch '^[A-Za-z]:') { throw 'Expected a local drive path.' }
        '/mnt/' + $full.Substring(0,1).ToLowerInvariant() + '/' + $full.Substring(3).Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    }
    $recipePath = [System.IO.Path]::Combine($sourceRoot, 'recipe.json')
    $recipe = Get-Content -LiteralPath $recipePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($recipe.release -cne $Release -or $recipe.clock_hz -ne 145125000 -or $recipe.clock_uncertainty_ns -ne 0.15) { throw 'Frozen release clock or uncertainty differs.' }
    $sourceInputs = [System.IO.Path]::Combine($sourceRoot, 'physical', 'V0', 'inputs')
    $inventory = @(Get-ChildItem -LiteralPath $sourceInputs -Recurse -File | Sort-Object FullName | ForEach-Object {
        [ordered]@{ relative_path = [System.IO.Path]::GetRelativePath($sourceInputs, $_.FullName).Replace([System.IO.Path]::DirectorySeparatorChar, '/'); sha256 = Get-Sha $_.FullName; size = $_.Length }
    })
    Save-Json ([System.IO.Path]::Combine($outputRoot, 'FROZEN_INPUT_HASHES.json')) $inventory
    $frozenCopy = [System.IO.Path]::Combine($outputRoot, 'frozen_inputs')
    if (-not (Test-Path -LiteralPath $frozenCopy)) { Copy-Item -LiteralPath $sourceInputs -Destination $frozenCopy -Recurse }
    foreach ($item in $inventory) {
        $copyPath = [System.IO.Path]::Combine($frozenCopy, $item.relative_path)
        if ((Get-Sha $copyPath) -cne $item.sha256) { throw ('Isolated frozen copy mismatch: ' + $item.relative_path) }
    }
    $firmware = [System.IO.Path]::Combine($sourceRoot, 'firmware', 'V0', 'firmware.hex')
    $physicalFirmware = [System.IO.Path]::Combine($sourceInputs, 'firmware.hex')
    $uart = [System.IO.Path]::Combine($sourceRoot, 'firmware', 'V0', 'uart.log')
    if ((Get-Sha $firmware) -cne $recipe.roles.V0.firmware_sha256 -or (Get-Sha $physicalFirmware) -cne $recipe.roles.V0.firmware_sha256) { throw 'Firmware hash differs from frozen recipe.' }
    if ((Get-Sha $uart) -cne $recipe.roles.V0.reference_uart_sha256) { throw 'Frozen UART hash differs from recipe.' }
    $reference = [System.IO.Path]::Combine($outputRoot, 'reference')
    [void][System.IO.Directory]::CreateDirectory($reference)
    foreach ($name in @('uart.log', 'simulation.log', 'simulation.command.json', 'firmware.elf', 'firmware.hex', 'build-manifest.json')) {
        Copy-Item -LiteralPath ([System.IO.Path]::Combine($sourceRoot, 'firmware', 'V0', $name)) -Destination ([System.IO.Path]::Combine($reference, $name)) -Force
    }
    $rtlEquality = @(Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($sourceRoot, 'simulation', 'inputs', 'rtl')) -File | Sort-Object Name | ForEach-Object {
        $physical = [System.IO.Path]::Combine($sourceInputs, 'rtl', $_.Name)
        $simHash = Get-Sha $_.FullName
        $physicalHash = Get-Sha $physical
        if ($simHash -cne $physicalHash) { throw ('Simulation and physical RTL differ: ' + $_.Name) }
        [ordered]@{ file = $_.Name; sha256 = $simHash; simulation_equals_physical = $true }
    })
    $corePath = [System.IO.Path]::Combine($sourceInputs, 'rtl', 'rv32_core.sv')
    $core = Get-Content -LiteralPath $corePath -Raw -Encoding utf8
    $semanticPatterns = [ordered]@{
        pipeline_order = 'assign\s+pipeline_valid=\{wb_valid,mem_valid,ex_valid,id_valid,if_valid\};'
        frontend_transfer = 'assign\s+frontend_fire=frontend_out_valid\s*&&\s*frontend_out_ready;'
        mem_completion = 'wire\s+mem_fire=mem_valid\s*&&'
        mem_redirect = 'wire\s+mem_flush=mem_fire\s*&&'
        wb_retirement = 'assign\s+trace_valid=wb_valid;'
        id_transfer = 'wire\s+id_fire=interrupt_pending\s*\?\s*id_fire_with_irq\s*:\s*id_fire_without_irq;'
        ex_transfer = 'wire\s+ex_fire=interrupt_pending\s*\?\s*ex_fire_with_irq\s*:\s*ex_fire_without_irq;'
        ex_pc_capture = 'ex_valid<=1;\s*ex_pc<=id_pc;'
        frontend_if_capture = 'if\(frontend_fire\)\s*begin\s*if_valid<=1;\s*if_pc<=frontend_pc;'
        flush_override = 'if\(frontend_flush\)\s*begin\s*if_valid<=0;\s*id_valid<=0;'
    }
    $semantics = @()
    foreach ($entry in $semanticPatterns.GetEnumerator()) {
        $matches = [regex]::Matches($core, $entry.Value)
        if ($matches.Count -ne 1) { throw ('Missing or ambiguous H3 semantic anchor: ' + $entry.Key) }
        $semantics += [ordered]@{ check = $entry.Key; matched = $matches[0].Value; pass = $true }
    }
    $symbols = [System.IO.Path]::Combine($outputRoot, 'COREMARK_SYMBOLS.txt')
    $nm = [System.IO.Path]::Combine($workspace, 'ZGTC_RISC_CPU', 'cpu_paper', 'tools', 'xpack-riscv-none-embed-gcc-10.2.0-1.2', 'bin', 'riscv-none-embed-nm')
    $elf = [System.IO.Path]::Combine($sourceRoot, 'firmware', 'V0', 'firmware.elf')
    $nmArguments = @('--cd', '/tmp', '--exec', (Convert-LinuxPath $nm), '-S', '-n', (Convert-LinuxPath $elf))
    $env:WSL_UTF8 = '1'
    $start = [System.Diagnostics.ProcessStartInfo]::new('wsl.exe')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $start.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    foreach ($argument in $nmArguments) { $start.ArgumentList.Add($argument) }
    $process = [System.Diagnostics.Process]::Start($start)
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(30000)) { $process.Kill($true); throw 'nm did not finish.' }
    $nmText = $stdoutTask.GetAwaiter().GetResult()
    $nmErr = $stderrTask.GetAwaiter().GetResult()
    [System.IO.File]::WriteAllText($symbols, $nmText, $utf8Bom)
    [System.IO.File]::WriteAllText([System.IO.Path]::Combine($outputRoot, 'nm.stderr.txt'), $nmErr, $utf8Bom)
    if ($process.ExitCode -ne 0) { throw ('nm exit=' + $process.ExitCode) }
    $selected = @()
    foreach ($name in @('main', 'iterate', 'core_bench_list', 'matrix_test', 'core_bench_matrix', 'core_bench_state', 'core_state_transition', 'start_time', 'stop_time', 'ee_printf')) {
        $match = [regex]::Match($nmText, '(?m)^([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+\S\s+' + [regex]::Escape($name) + '\s*$')
        if (-not $match.Success) { throw ('ELF function missing: ' + $name) }
        $selected += [ordered]@{ function = $name; start = '0x' + $match.Groups[1].Value; size_bytes = [Convert]::ToUInt32($match.Groups[2].Value, 16); trigger = 'EX_PC == 0x' + $match.Groups[1].Value + ' AND ex_fire == 1' }
    }
    $uartText = Get-Content -LiteralPath $uart -Raw -Encoding utf8
    $performance = [regex]::Match($uartText, 'ZGTC cycles_hex=([0-9a-fA-F]+) retired_hex=([0-9a-fA-F]+) clock_hz=(\d+)')
    if (-not $performance.Success) { throw 'Frozen UART performance counters missing.' }
    $map = @()
    for ($bit = 0; $bit -lt 32; $bit++) { $map += [ordered]@{ channel = $bit; source = ('board/soc/core/ex_pc[' + $bit + ']'); meaning = ('EX PC bit ' + $bit) } }
    $rest = @(
        @('if_valid', 'IF occupied'), @('id_valid', 'ID occupied'), @('ex_valid', 'EX occupied'), @('mem_valid', 'MEM occupied'), @('wb_valid', 'WB retire event'),
        @('id_fire', 'ID transfers to EX'), @('ex_fire', 'EX transfers to MEM'), @('mem_flush', 'MEM causes frontend redirect'), @('frontend_fire', 'Frontend transfers an instruction to IF'), @('mem_fire', 'MEM completion event')
    )
    for ($index = 0; $index -lt $rest.Count; $index++) { $map += [ordered]@{ channel = 32 + $index; source = 'board/soc/core/' + $rest[$index][0]; meaning = $rest[$index][1] } }
    $result = [ordered]@{
        schema = 'h3-minimal-ila-independent-source-qualification/v1'; release = $Release; qualified_utc = [datetime]::UtcNow.ToString('o')
        frozen_recipe = $recipePath; frozen_recipe_sha256 = Get-Sha $recipePath; frozen_input_root = $sourceInputs; isolated_frozen_copy = $frozenCopy
        input_count = $inventory.Count; original_inputs_unchanged = $true; physical_simulation_rtl = $rtlEquality
        clock_hz = $recipe.clock_hz; expected_period_ns = 1e9 / $recipe.clock_hz; uncertainty_ns = $recipe.clock_uncertainty_ns; pnr_options = $recipe.roles.V0.pnr_options
        firmware_hex_sha256 = Get-Sha $firmware; firmware_elf_sha256 = Get-Sha $elf; reference_uart_sha256 = Get-Sha $uart
        reference_cycles_hex = $performance.Groups[1].Value; reference_cycles = [Convert]::ToUInt64($performance.Groups[1].Value, 16)
        reference_retired_hex = $performance.Groups[2].Value; reference_retired = [Convert]::ToUInt64($performance.Groups[2].Value, 16)
        reference_full_coremark_completed = $uartText.Contains('Correct operation validated.') -and $uartText.Contains('ZGTC COREMARK FINISHED')
        nm_command = @('wsl.exe') + $nmArguments; nm_exit_code = $process.ExitCode; key_functions = $selected
        sample_clock = 'cpu_clk'; data_width = 42; trigger_width = 42; data_equals_trigger = $true; capture_depth = 1024; channels = $map
        source_semantics = $semantics
        scope = 'Source/firmware identity and signal semantics. Physical net names, capture correctness, final ILA timing, and board UART require separate generated evidence.'
    }
    Save-Json ([System.IO.Path]::Combine($outputRoot, 'SOURCE_QUALIFICATION.json')) $result
    $notes = @(
        ('H3 source qualification: ' + $Release),
        ('Firmware V0 SHA256: ' + $result.firmware_hex_sha256),
        ('Frozen completed CoreMark: cycles=' + $result.reference_cycles + '; retired=' + $result.reference_retired),
        'Data and trigger each use 42 bits with identical ordering; dataEqualsTrigger=true; depth=1024; sampling clock=cpu_clk.',
        'Channels 0..31=EX PC; 32=IF valid; 33=ID valid; 34=EX valid; 35=MEM valid; 36=WB valid; 37=id_fire; 38=ex_fire; 39=mem_flush; 40=frontend_fire; 41=mem_fire.',
        'Trigger each function with its exact ELF entry PC and ex_fire=1. Wildcard all remaining trigger bits.',
        'pipeline_valid[4:0]={WB,MEM,EX,ID,IF}. Stage validity measures occupancy; the fire signals distinguish held instructions from transfers.',
        'frontend_fire is frontend_out_valid && frontend_out_ready. It marks instruction delivery to IF, not a raw cache response. A simultaneous frontend_flush or frontend_barrier cancels the IF update.',
        'mem_flush covers MEM faults, MRET, FENCE.I, and unresolved prediction miss. Earlier ID/EX redirects are observable indirectly through validity changes, but the minimal map does not identify their cause.',
        'EX PC has meaning for this map only with EX valid; ex_fire makes a function-entry trigger a transfer event and avoids repeated hits during a stall.',
        'The map supports occupancy, transfer cadence, EX hold time, MEM completion, and MEM flush timing. It does not uniquely classify all stall causes or reconstruct all stage PCs.',
        'Only passive synthesis-preservation attributes and ILA insertion are intended. Each release must retain its own UART/cycle reference; Base and Retained intentionally have different cycle totals.'
    )
    [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($outputRoot, 'PROBE_SEMANTICS.txt'), $notes, $utf8Bom)
    foreach ($path in @('FROZEN_INPUT_HASHES.json', 'COREMARK_SYMBOLS.txt', 'SOURCE_QUALIFICATION.json', 'PROBE_SEMANTICS.txt')) {
        $actual = [System.IO.Path]::Combine($outputRoot, $path)
        if ([string]::IsNullOrWhiteSpace([System.IO.File]::ReadAllText($actual))) { throw ('Artifact empty: ' + $path) }
    }
    Write-Output ('SOURCE_QUALIFIED release=' + $Release + ' rtl_files=' + $rtlEquality.Count + ' functions=' + $selected.Count + ' data=42 trigger=42 clock_hz=145125000 uncertainty_ns=0.15')
    Write-Output ('SOURCE_QUALIFICATION=' + [System.IO.Path]::Combine($outputRoot, 'SOURCE_QUALIFICATION.json'))
    exit 0
} catch {
    Write-Error $_
    exit 1
}
