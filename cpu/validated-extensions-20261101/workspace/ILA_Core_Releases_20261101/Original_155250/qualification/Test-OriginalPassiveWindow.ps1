param(
    [ValidateSet('Original_155250')][string]$Release = 'Original_155250',
    [ValidateSet('BASELINE', 'MODIFIED', 'ROLLBACK')][string]$Variant = 'BASELINE',
    [ValidateLength(0, 500)][string]$BuildDirectory = '',
    [ValidateRange(100000, 10000000)][long]$Cycles = 2000000
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $workspace = [System.IO.Path]::Combine('D:', 'AAAFPGA')
    $taskRoot = [System.IO.Path]::Combine($workspace, 'ILA_Core_Releases_20261101')
    $sourceRoot = [System.IO.Path]::Combine($workspace, 'Current_Paper_and_Sub7000_Core_Releases_20261012', 'cores', $Release)
    $qualification = [System.IO.Path]::Combine($taskRoot, $Release, 'qualification')
    $root = [System.IO.Path]::Combine($qualification, 'dynamic', $Variant)
    $utf8Bom = [System.Text.UTF8Encoding]::new($true)
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    function Save-Json([string]$Path, [object]$Value) { [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 25), $utf8Bom) }
    function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    function Convert-LinuxPath([string]$Path) {
        $full = [System.IO.Path]::GetFullPath($Path)
        if ($full -notmatch '^[A-Za-z]:') { throw 'Expected local drive path.' }
        '/mnt/' + $full.Substring(0,1).ToLowerInvariant() + '/' + $full.Substring(3).Replace([System.IO.Path]::DirectorySeparatorChar, '/')
    }
    function Replace-Unique([string]$Text, [string]$Before, [string]$After) {
        if ([regex]::Matches($Text, [regex]::Escape($Before)).Count -ne 1) { throw ('Source edit anchor is not unique: ' + $Before.Substring(0, [math]::Min(90,$Before.Length))) }
        $Text.Replace($Before, $After)
    }
    function Run-Wsl([string[]]$Arguments, [string]$LogPrefix, [int]$TimeoutSeconds) {
        $info = [System.Diagnostics.ProcessStartInfo]::new('wsl.exe')
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $info.StandardErrorEncoding = [System.Text.Encoding]::UTF8
        foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
        $started = [datetime]::UtcNow
        $process = [System.Diagnostics.Process]::Start($info)
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { $process.Kill($true); throw ('Timeout: ' + $LogPrefix) }
        $outText = $outTask.GetAwaiter().GetResult()
        $errText = $errTask.GetAwaiter().GetResult()
        [System.IO.File]::WriteAllText(($LogPrefix + '.stdout.log'), $outText, $utf8Bom)
        [System.IO.File]::WriteAllText(($LogPrefix + '.stderr.log'), $errText, $utf8Bom)
        $receipt = [ordered]@{ executable = 'wsl.exe'; arguments = $Arguments; actual_exit_code = $process.ExitCode; started_utc = $started.ToString('o'); finished_utc = [datetime]::UtcNow.ToString('o'); stdout = $LogPrefix + '.stdout.log'; stderr = $LogPrefix + '.stderr.log' }
        Save-Json ($LogPrefix + '.command.json') $receipt
        if ($process.ExitCode -ne 0) { throw ('Command failed exit=' + $process.ExitCode + '; log=' + $LogPrefix) }
        return $outText
    }
    $sourceInputs = [System.IO.Path]::Combine($sourceRoot, 'physical', 'V0', 'inputs')
    if ($Variant -ne 'BASELINE') {
        if ([string]::IsNullOrWhiteSpace($BuildDirectory)) { throw 'Modified and rollback tests require a concrete build directory.' }
        $canonicalBuild = [System.IO.Path]::GetFullPath($BuildDirectory)
        $releasePrefix = [System.IO.Path]::Combine($taskRoot, $Release) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $canonicalBuild.StartsWith($releasePrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Build directory must be inside this isolated release.' }
        $sourceInputs = [System.IO.Path]::Combine($canonicalBuild, 'inputs')
        if ($Variant -eq 'ROLLBACK') {
            $sourceInputs = [System.IO.Path]::Combine($canonicalBuild, 'rollback_test', 'inputs')
            $rollbackScript = [System.IO.Path]::Combine($canonicalBuild, 'ROLLBACK.ps1')
            $rollbackOutput = @(& pwsh -NoProfile -File $rollbackScript -BuildDirectory $canonicalBuild -TargetDirectory $sourceInputs)
            if ($LASTEXITCODE -ne 0) { throw 'Separate-copy rollback failed.' }
            Write-Output ($rollbackOutput -join "`n")
        }
    }
    if (-not (Test-Path -LiteralPath $sourceInputs -PathType Container)) { throw 'Source input directory missing.' }
    [void][System.IO.Directory]::CreateDirectory($root)
    $inputs = [System.IO.Path]::Combine($root, 'inputs')
    if (-not (Test-Path -LiteralPath $inputs)) { [void][System.IO.Directory]::CreateDirectory($inputs) }
    $rtlDest = [System.IO.Path]::Combine($inputs, 'rtl')
    if (-not (Test-Path -LiteralPath $rtlDest)) { Copy-Item -LiteralPath ([System.IO.Path]::Combine($sourceInputs, 'rtl')) -Destination $rtlDest -Recurse }
    $simDest = [System.IO.Path]::Combine($inputs, 'sim')
    if (-not (Test-Path -LiteralPath $simDest)) { Copy-Item -LiteralPath ([System.IO.Path]::Combine($sourceRoot, 'simulation', 'inputs', 'sim')) -Destination $simDest -Recurse }
    $sourceHashes = @()
    foreach ($file in Get-ChildItem -LiteralPath $rtlDest -File | Sort-Object Name) {
        $origin = [System.IO.Path]::Combine($sourceInputs, 'rtl', $file.Name)
        if ((Get-Sha $origin) -cne (Get-Sha $file.FullName)) { throw ('Existing dynamic copy differs from requested source: ' + $file.Name) }
        $sourceHashes += [ordered]@{ file=$file.Name; sha256=Get-Sha $file.FullName }
    }
    $observerPath = [System.IO.Path]::Combine($simDest, 'rv32_observed_soc.sv')
    $observer = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($sourceRoot, 'simulation', 'inputs', 'sim', 'rv32_observed_soc.sv')).Replace("`r`n", "`n")
    $observer = Replace-Unique $observer 'output wire [2:0] redirect_kind' ('output wire [41:0] ila_capture_data,' + "`n" + '    output wire [2:0] redirect_kind')
    $observations = @(
        '    assign ila_capture_data={soc.core.mem_fire,soc.core.frontend_fire,soc.core.mem_flush,soc.core.ex_fire,soc.core.id_fire,',
        '        soc.core.wb_valid,soc.core.mem_valid,soc.core.ex_valid,soc.core.id_valid,soc.core.if_valid,soc.core.ex_pc};',
        '    always @(posedge clk) if(rst_n) begin',
        '        if(soc.core.id_fire && !soc.core.id_valid) $fatal(1,"ILA semantic check: ID fire without valid");',
        '        if(soc.core.ex_fire && !soc.core.ex_valid) $fatal(1,"ILA semantic check: EX fire without valid");',
        '        if(soc.core.mem_fire && !soc.core.mem_valid) $fatal(1,"ILA semantic check: MEM fire without valid");',
        '        if(soc.core.mem_flush && !soc.core.mem_fire) $fatal(1,"ILA semantic check: MEM flush without fire");',
        '        if(soc.core.pipeline_valid !== {soc.core.wb_valid,soc.core.mem_valid,soc.core.ex_valid,soc.core.id_valid,soc.core.if_valid})',
        '            $fatal(1,"ILA semantic check: pipeline bus ordering");',
        '    end'
    ) -join "`n"
    $observer = Replace-Unique $observer 'endmodule' ($observations + "`nendmodule")
    [System.IO.File]::WriteAllText($observerPath, $observer, $utf8NoBom)
    $driverPath = [System.IO.Path]::Combine($simDest, 'driver.cpp')
    $driver = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($sourceRoot, 'simulation', 'inputs', 'sim', 'driver.cpp')).Replace("`r`n", "`n")
    $driver = Replace-Unique $driver 'uint64_t redirects[7] = {}' ('uint64_t ila_hash = 1469598103934665603ULL, trace_hash = 1469598103934665603ULL;' + "`n" + '        uint64_t signal_cycles[10] = {}, function_entries[4] = {};' + "`n" + '        uint64_t redirects[7] = {}')
    $hashStep = @(
        '            uint64_t sample = model->ila_capture_data;',
        '            ila_hash = (ila_hash ^ sample) * 1099511628211ULL;',
        '            for (unsigned s=0; s<10; ++s) signal_cycles[s] += (sample >> (32+s)) & 1ULL;',
        '            if ((sample >> 38) & 1ULL) {',
        '                const uint32_t entry_pc[4] = {0x88U, 0x942U, 0x2604U, 0x2e18U};',
        '                for (unsigned e=0; e<4; ++e) if (uint32_t(sample) == entry_pc[e]) ++function_entries[e];',
        '            }',
        '            if (model->trace_valid) {',
        '                trace_hash = (trace_hash ^ (uint64_t(model->trace_pc) << 32) ^ model->trace_instruction) * 1099511628211ULL;',
        '            }',
        '            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;'
    ) -join "`n"
    $driver = Replace-Unique $driver '            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;' $hashStep
    $end = @(
        '        if (model->trap_valid || model->maintenance_fault) throw std::runtime_error("Window ended with a trap");',
        '        uart.flush();',
        '        if (!uart) throw std::runtime_error("Window UART write failed");',
        '        std::cout << "PARTIAL_WINDOW_PASS cycle_limit=" << max_cycles << " cycle_count=" << model->cycle_count',
        '            << " retired=" << model->retired_count << " snapshots=" << sequence << " status_code=0x" << std::hex << model->status_code',
        '            << " ila_hash=0x" << ila_hash << " trace_hash=0x" << trace_hash << std::dec << ''\n'';',
        '        std::cout << "SIGNAL_CYCLES"; for (unsigned s=0; s<10; ++s) std::cout << " " << signal_cycles[s]; std::cout << ''\n'';',
        '        std::cout << "FUNCTION_ENTRIES iterate=" << function_entries[0] << " list=" << function_entries[1]',
        '            << " matrix=" << function_entries[2] << " state=" << function_entries[3] << ''\n'';',
        '        model->final();',
        '        return 0;'
    ) -join "`n"
    $driver = Replace-Unique $driver '        throw std::runtime_error("RTL cycle limit exceeded");' $end
    [System.IO.File]::WriteAllText($driverPath, $driver, $utf8NoBom)
    $firmware = [System.IO.Path]::Combine($root, 'firmware.hex')
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($sourceInputs, 'firmware.hex')) -Destination $firmware -Force
    $recipe = Get-Content -LiteralPath ([System.IO.Path]::Combine($sourceRoot, 'recipe.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    if ((Get-Sha $firmware) -cne $recipe.roles.V0.firmware_sha256) { throw 'Dynamic test firmware differs from frozen V0.' }
    $arguments = @($recipe.simulation.argv | ForEach-Object {
        $_.Replace('{RELEASE}/simulation/inputs', (Convert-LinuxPath $inputs)).Replace('{OUTPUT}', (Convert-LinuxPath $root))
    })
    $jobsIndex = [array]::IndexOf($arguments, '-j')
    $arguments[$jobsIndex+1] = '1'
    $verilator = $recipe.simulation.tool_original
    $env:WSL_UTF8 = '1'
    Save-Json ([System.IO.Path]::Combine($root, 'SOURCE_IDENTITY.json')) ([ordered]@{ release=$Release; variant=$Variant; source_inputs=$sourceInputs; rtl=$sourceHashes; firmware_sha256=Get-Sha $firmware; observer_sha256=Get-Sha $observerPath; driver_sha256=Get-Sha $driverPath; cycle_limit=$Cycles; purpose='Short unchanged-firmware dynamic equality window; this is not a completed CoreMark run.' })
    $exePath = [System.IO.Path]::Combine($root, 'objects', 'Vrv32_observed_soc')
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        Write-Output ('DYNAMIC_BUILD release=' + $Release + ' variant=' + $Variant)
        $null = Run-Wsl (@('--cd', '/tmp', '--exec', $verilator) + $arguments) ([System.IO.Path]::Combine($root, 'compile')) 600
    }
    $uartPath = [System.IO.Path]::Combine($root, 'uart.log')
    Write-Output ('DYNAMIC_RUN release=' + $Release + ' variant=' + $Variant + ' cycles=' + $Cycles)
    $runText = Run-Wsl @('--cd', (Convert-LinuxPath $root), '--exec', (Convert-LinuxPath $exePath), (Convert-LinuxPath $uartPath), $Cycles.ToString([System.Globalization.CultureInfo]::InvariantCulture)) ([System.IO.Path]::Combine($root, 'run')) 120
    if ($runText -notmatch 'PARTIAL_WINDOW_PASS' -or $runText -notmatch 'FUNCTION_ENTRIES iterate=[1-9]\d* list=[1-9]\d* matrix=[1-9]\d* state=[1-9]\d*') { throw 'Dynamic window did not exercise all key CoreMark functions.' }
    $uartText = [System.IO.File]::ReadAllText($uartPath)
    if ($uartText -notmatch 'ZGTC COREMARK READY' -or $uartText -notmatch 'ZGTC COREMARK START iterations=6000 validation=0') { throw 'Dynamic UART did not confirm unchanged 6000-iteration firmware startup.' }
    $result = [ordered]@{ release=$Release; variant=$Variant; dynamic_window_completed=$true; complete_coremark=$false; cycle_limit=$Cycles; firmware_sha256=Get-Sha $firmware; uart_sha256=Get-Sha $uartPath; run_stdout_sha256=Get-Sha ([System.IO.Path]::Combine($root, 'run.stdout.log')); exact_output=$runText; source_inputs=$sourceInputs; run_exit_code=0 }
    if ($Variant -ne 'BASELINE') {
        $baseline = [System.IO.Path]::Combine($qualification, 'dynamic', 'BASELINE')
        $baselineResult = Get-Content -LiteralPath ([System.IO.Path]::Combine($baseline, 'RESULT.json')) -Raw -Encoding utf8 | ConvertFrom-Json
        if ($result.firmware_sha256 -cne $baselineResult.firmware_sha256 -or $result.uart_sha256 -cne $baselineResult.uart_sha256 -or $result.exact_output -cne $baselineResult.exact_output) { throw 'Baseline and candidate dynamic observations differ.' }
        $result['baseline_uart_equal'] = $true
        $result['baseline_cycles_trace_and_42_probes_equal'] = $true
    }
    Save-Json ([System.IO.Path]::Combine($root, 'RESULT.json')) $result
    foreach ($path in @('SOURCE_IDENTITY.json','RESULT.json','run.command.json','run.stdout.log','uart.log')) { $null = [System.IO.File]::ReadAllText([System.IO.Path]::Combine($root,$path)) }
    Write-Output $runText.Trim()
    Write-Output ('DYNAMIC_RESULT=' + [System.IO.Path]::Combine($root,'RESULT.json'))
    exit 0
} catch {
    Write-Error $_
    exit 1
}
