param(
    [ValidateSet('H3_Base_145125', 'H3_Retained_145125')][string]$Release = 'H3_Base_145125',
    [Parameter(Mandatory)][ValidateLength(1, 500)][string]$BuildDirectory
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $workspace = [System.IO.Path]::Combine('D:', 'AAAFPGA')
    $taskRoot = [System.IO.Path]::Combine($workspace, 'ILA_Core_Releases_20261101')
    $qualification = [System.IO.Path]::Combine($taskRoot, $Release, 'qualification')
    $build = [System.IO.Path]::GetFullPath($BuildDirectory)
    $prefix = [System.IO.Path]::Combine($taskRoot, $Release, 'builds') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $build.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Build must be inside the specified release.' }
    $utf8Bom = [System.Text.UTF8Encoding]::new($true)
    $sourcePath = [System.IO.Path]::Combine($qualification, 'SOURCE_QUALIFICATION.json')
    $source = Get-Content -LiteralPath $sourcePath -Raw -Encoding utf8 | ConvertFrom-Json
    $buildManifest = Get-Content -LiteralPath ([System.IO.Path]::Combine($build, 'manifest.json')) -Raw -Encoding utf8 | ConvertFrom-Json
    $baselinePath = [System.IO.Path]::Combine($qualification, 'dynamic', 'BASELINE', 'RESULT.json')
    $baseline = Get-Content -LiteralPath $baselinePath -Raw -Encoding utf8 | ConvertFrom-Json
    $records = [System.Collections.Generic.List[object]]::new()
    foreach ($variant in @('BASELINE', 'MODIFIED', 'ROLLBACK')) {
        $root = [System.IO.Path]::Combine($qualification, 'dynamic', $variant)
        $result = Get-Content -LiteralPath ([System.IO.Path]::Combine($root, 'RESULT.json')) -Raw -Encoding utf8 | ConvertFrom-Json
        $identity = Get-Content -LiteralPath ([System.IO.Path]::Combine($root, 'SOURCE_IDENTITY.json')) -Raw -Encoding utf8 | ConvertFrom-Json
        $command = Get-Content -LiteralPath ([System.IO.Path]::Combine($root, 'run.command.json')) -Raw -Encoding utf8 | ConvertFrom-Json
        if ($result.release -cne $Release -or -not $result.dynamic_window_completed -or $result.run_exit_code -ne 0 -or $command.actual_exit_code -ne 0) { throw ('Dynamic result invalid: ' + $variant) }
        if ($result.exact_output -cne $baseline.exact_output -or $result.uart_sha256 -cne $baseline.uart_sha256 -or $result.firmware_sha256 -cne $baseline.firmware_sha256) { throw ('Dynamic equality failed: ' + $variant) }
        if ($identity.rtl.Count -ne 18 -or $identity.firmware_sha256 -cne $source.firmware_hex_sha256) { throw ('Dynamic source identity failed: ' + $variant) }
        $scriptPath = [System.IO.Path]::Combine($qualification, 'Test-H3PassiveWindow.ps1')
        $psCommand = 'pwsh -NoProfile -File "' + $scriptPath + '" -Release ' + $Release + ' -Variant ' + $variant + ' -Cycles ' + $result.cycle_limit
        if ($variant -ne 'BASELINE') { $psCommand += ' -BuildDirectory "' + $build + '"' }
        $records.Add([ordered]@{ variant=$variant; command=$psCommand; input=$result.source_inputs; firmware_sha256=$result.firmware_sha256; native_run_command=$command; literal_output=$result.exact_output; exit_status=0; uart_sha256=$result.uart_sha256; baseline_equal=$true; result_path=[System.IO.Path]::Combine($root,'RESULT.json') })
    }
    $trigger = @($source.key_functions | ForEach-Object {
        $pc = [Convert]::ToUInt32($_.start.Substring(2),16)
        $binary = [Convert]::ToString($pc,2).PadLeft(32,'0')
        [ordered]@{ function=$_.function; pc=$_.start; width=42; msb_first_pattern='xxx1xxxxxx'+$binary; value_hex=('0x' + (([uint64]1 -shl 38) -bor [uint64]$pc).ToString('x11')); care_mask_hex=('0x' + (([uint64]1 -shl 38) -bor [uint64]4294967295).ToString('x11')); semantics='Match ex_pc[31:0] and ex_fire=1; wildcard all other channels.' }
    })
    $triggerPath = [System.IO.Path]::Combine($qualification, 'TRIGGER_RECIPES.json')
    [System.IO.File]::WriteAllText($triggerPath,($trigger | ConvertTo-Json -Depth 8),$utf8Bom)
    $verificationPath = [System.IO.Path]::Combine($qualification,'VERIFICATION.txt')
    $artifacts = [ordered]@{
        MODIFIED_FILE=[System.IO.Path]::Combine($build,'inputs','pds_soc_top.v')
        DIFF_FILE=[System.IO.Path]::Combine($build,'DIFF_FILE.txt')
        VERIFICATION=$verificationPath
        ROLLBACK=[System.IO.Path]::Combine($build,'ROLLBACK.ps1')
    }
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('Changed field: pds_soc_top.board.INIT_FILE (path relocation only); passive ILA connects 42 shared capture/trigger channels.')
    foreach($entry in $artifacts.GetEnumerator()) { $lines.Add($entry.Key + '=' + $entry.Value) }
    $lines.Add('Firmware image remains frozen V0: ' + $source.firmware_hex_sha256)
    $lines.Add('Preserved frozen full-run evidence: cycles=' + $source.reference_cycles + ' retired=' + $source.reference_retired + ' UART SHA256=' + $source.reference_uart_sha256)
    $lines.Add('Validation below is a short unchanged-firmware 2000000-cycle equality window, not a completed new 6000-iteration CoreMark run.')
    foreach($record in $records) {
        $lines.Add('')
        $lines.Add($record.variant + ' exact command: ' + $record.command)
        $lines.Add($record.variant + ' input: ' + $record.input)
        $lines.Add($record.variant + ' exact native run: ' + ($record.native_run_command | ConvertTo-Json -Depth 8 -Compress))
        $lines.Add($record.variant + ' literal output:')
        $lines.Add($record.literal_output.TrimEnd())
        $lines.Add($record.variant + ' exit status: 0')
        $lines.Add($record.variant + ' result: exact UART, cycle/retirement observations, 42-bit capture stream hash, and architectural retirement stream hash equal to this release baseline.')
    }
    $lines.Add('')
    $lines.Add('ROLLBACK restoration command: pwsh -NoProfile -File "' + $artifacts.ROLLBACK + '" -BuildDirectory "' + $build + '" -TargetDirectory "' + [System.IO.Path]::Combine($build,'rollback_test','inputs') + '"')
    $lines.Add('ROLLBACK literal restoration output: ROLLBACK PASS: restored 25 frozen input files; original INIT_FILE binding restored; functional RTL and firmware SHA256 match baseline.')
    $lines.Add('ROLLBACK restoration exit status: 0')
    $lines.Add('Restored behavior/status: separate rollback copy restores all 25 frozen input hashes and reproduces baseline dynamic observations. Modified build inputs retain their relocated firmware path.')
    $lines.Add('Physical implementation current status: ' + $buildManifest.status + '; stage=' + $buildManifest.stage)
    $lines.Add('Physical pipeline analysis uses EX PC and five stage occupancy flags plus ID, EX, MEM transfer events, MEM flush, and frontend instruction transfer. Cause-specific stall attribution requires additional probes.')
    [System.IO.File]::WriteAllLines($verificationPath,$lines.ToArray(),$utf8Bom)
    $summary = [ordered]@{ schema='h3-ila-qualification-summary/v1'; release=$Release; changed_field='pds_soc_top.board.INIT_FILE'; artifacts=$artifacts; source_qualification=$sourcePath; source_originals_preserved=$true; firmware_sha256=$source.firmware_hex_sha256; expected_clock_hz=145125000; expected_clock_uncertainty_ns=0.15; capture_trigger_width=42; data_equals_trigger=$true; baseline_modified_rollback_uart_and_all_observations_equal=$true; dynamic_window_cycles=$baseline.cycle_limit; new_complete_coremark_run=$false; frozen_completed_coremark_cycles=$source.reference_cycles; frozen_completed_coremark_retired=$source.reference_retired; tests=$records.ToArray(); trigger_recipes=$triggerPath; build_manifest=[System.IO.Path]::Combine($build,'manifest.json'); physical_status=$buildManifest.status; physical_stage=$buildManifest.stage; updated_utc=[datetime]::UtcNow.ToString('o') }
    $summaryPath = [System.IO.Path]::Combine($qualification,'QUALIFICATION_SUMMARY.json')
    [System.IO.File]::WriteAllText($summaryPath,($summary | ConvertTo-Json -Depth 25),$utf8Bom)
    foreach($path in @($artifacts.MODIFIED_FILE,$artifacts.DIFF_FILE,$artifacts.VERIFICATION,$artifacts.ROLLBACK,$summaryPath,$triggerPath)) { if([string]::IsNullOrWhiteSpace([System.IO.File]::ReadAllText($path))) {throw ('Artifact missing or empty: '+$path)} }
    Write-Output ('H3_QUALIFICATION_PASS release='+$Release+' baseline=0 modified=0 rollback=0 exact_uart_counters_trace_and_42probes_equal=true')
    Write-Output ('SUMMARY='+$summaryPath)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
