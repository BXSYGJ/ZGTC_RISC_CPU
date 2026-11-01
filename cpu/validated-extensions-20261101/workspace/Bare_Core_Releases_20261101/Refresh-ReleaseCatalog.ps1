[CmdletBinding()]
param([switch]$AllowIncomplete)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $root = $PSScriptRoot
    $utf8Bom = [System.Text.UTF8Encoding]::new($true)
    $rows = [System.Collections.Generic.List[object]]::new()
    foreach ($release in @('Original_155250', 'H3_Retained_145125', 'H3_Base_145125')) {
        $selectedPath = [System.IO.Path]::Combine($root, $release, 'SELECTED_BUILD.json')
        if (-not (Test-Path -LiteralPath $selectedPath)) { if ($AllowIncomplete) { continue }; throw ('Selection incomplete: ' + $release) }
        $selected = Get-Content -LiteralPath $selectedPath -Raw -Encoding utf8 | ConvertFrom-Json
        foreach ($field in @('manifest', 'resource_timing_report', 'fixture_test', 'physical_fixture', 'core_attribution_report', 'source_manifest', 'extraction_qualification', 'verification')) {
            $hashField = $field + '_sha256'
            if ((Get-FileHash -LiteralPath $selected.$field -Algorithm SHA256).Hash -ine $selected.$hashField) { throw ('Selected evidence changed: ' + $selected.$field) }
        }
        if (-not $selected.all_corner_timing_passed -or -not $selected.setup_uncertainty_satisfies_minimum -or $selected.actual_setup_uncertainty_ns -lt 0.150) { throw ('Selected timing is incomplete: ' + $release) }
        if ($selected.functional_rtl_changes -ne 0 -or $selected.hardware_validated) { throw 'Unexpected implementation provenance.' }
        $source = Get-Content -LiteralPath $selected.source_manifest -Raw -Encoding utf8 | ConvertFrom-Json
        if (@($source.rtl).Count -ne 8) { throw 'Unexpected core source closure.' }
        foreach ($file in $source.rtl) { if ((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash -ine $file.sha256) { throw ('Core source changed: ' + $file.name) } }
        $miter = Get-Content -LiteralPath $selected.extraction_qualification -Raw -Encoding utf8 | ConvertFrom-Json
        if ($miter.status -ne 'PASS' -or -not $miter.restored_behavior_equal -or $miter.baseline.exit_code -ne 0 -or $miter.modified_negative_control.exit_code -ne 1 -or $miter.rollback.exit_code -ne 0) { throw ('Extraction qualification failed: ' + $release) }
        $ilaSelectedPath = [System.IO.Path]::Combine([System.IO.Path]::GetFullPath([System.IO.Path]::Combine($root, '..')), 'ILA_Core_Releases_20261101', $release, 'SELECTED_BUILD.json')
        $ilaSelected = Get-Content -LiteralPath $ilaSelectedPath -Raw -Encoding utf8 | ConvertFrom-Json
        $fullPath = [System.IO.Path]::Combine($ilaSelected.full_simulation_directory, 'RESULT.json')
        $full = Get-Content -LiteralPath $fullPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($release -eq 'Original_155250') {
            if (-not $full.complete_coremark_run -or $full.exit_code -ne 0 -or -not $full.uart_byte_identical) { throw 'Full source run failed.' }
            $cycles = [long]$full.cycle_count; $retired = [long]$full.retired_count
        } else {
            if (-not $full.completed_6000_iterations -or $full.native_exit_code -ne 0 -or -not $full.exact_reference_uart_equal) { throw 'Full source run failed.' }
            $cycles = [long]$full.cycles; $retired = [long]$full.retired
        }
        $areaMin = [int]$selected.core_resources.physical_lut_lower_bound
        $areaMax = [int]$selected.core_resources.physical_lut_upper_bound
        if ($areaMin -lt 1 -or $areaMax -lt $areaMin) { throw 'Invalid core area bound.' }
        $totalLut = [int]$selected.resources_total.lut
        $reconciled = $areaMin + [int]$selected.fixture_resources.physical_exclusive_lut + [int]$selected.shared_lut_sites + [int]$selected.unattributed_lut_slots
        if ($totalLut -ne $reconciled) { throw 'Physical LUT allocation does not reconcile.' }
        if ($areaMax -ne ($areaMin + [int]$selected.shared_lut_sites + [int]$selected.unattributed_lut_slots)) { throw 'Conservative core area bound does not cover every unallocated LUT site.' }
        if ([int]$selected.resources_total.ff -ne ([int]$selected.core_resources.ff + [int]$selected.fixture_resources.ff)) { throw 'Physical FF allocation does not reconcile.' }
        $perMHz = 6000.0 * 1e6 / $cycles
        $score = $perMHz * $selected.clock_hz / 1e6
        $rows.Add([ordered]@{
            release = $release; selection = $selectedPath; selection_sha256 = (Get-FileHash -LiteralPath $selectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
            build_directory = $selected.build_directory; clock_hz = $selected.clock_hz; setup_slack_ns = $selected.setup_wns_ns; timing_passed = $true
            minimum_uncertainty_ns = $selected.requested_minimum_setup_uncertainty_ns; effective_uncertainty_ns = $selected.actual_setup_uncertainty_ns
            core_lut_min = $areaMin; core_lut_conservative = $areaMax; core_ff = $selected.core_resources.ff; core_drm = $selected.core_resources.DRM; core_apm = $selected.core_resources.APM
            core_distributed_ram_lut_sites = $selected.core_resources.distributed_ram_lut_sites; core_area_report = $selected.core_attribution_report
            fixture_lut_exclusive = $selected.fixture_resources.physical_exclusive_lut; fixture_ff = $selected.fixture_resources.ff
            shared_lut_sites = $selected.shared_lut_sites; unattributed_lut_slots = $selected.unattributed_lut_slots; whole_fixture_lut = $totalLut; whole_fixture_ff = $selected.resources_total.ff
            source_full_simulation = $fullPath; source_full_simulation_sha256 = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
            cycles = $cycles; retired = $retired; source_coremark_per_mhz = $perMHz; target_clock_derived_coremark = $score
            coremark_per_lut_lower = $score / $areaMax; coremark_per_lut_upper = $score / $areaMin
            coremark_per_mhz_per_klut_lower = $perMHz * 1000 / $areaMax; coremark_per_mhz_per_klut_upper = $perMHz * 1000 / $areaMin
            efficiency_scope = 'Core-only physical area with explicitly external cached-system services; finite extraction miter plus exact source join to completed 6000-iteration source executions.'
            extraction_qualification = $selected.extraction_qualification; fresh_full_bare_run = $false; hardware_validated = $false; functional_rtl_changes = 0
        })
    }
    $catalog = [ordered]@{ schema = 'independent-bare-core-releases/v1'; status = if ($rows.Count -eq 3) { 'complete' } else { 'partial' }; generated_utc = [datetime]::UtcNow.ToString('o'); releases = $rows.ToArray(); area_metric = 'Conservative core physical LUT bound assigns all shared and unattributed LUT sites to the CPU.'; memory_service = 'Existing cached memory and system services remain outside the synthesized DUT.'; remote_operations = 'disabled by user' }
    $catalogPath = [System.IO.Path]::Combine($root, 'RELEASES.json')
    [System.IO.File]::WriteAllText($catalogPath, ($catalog | ConvertTo-Json -Depth 30), $utf8Bom)
    $report = [System.Collections.Generic.List[string]]::new()
    $report.Add('# Bare-core resource efficiency'); $report.Add('')
    $report.Add('The physical CPU DUT contains no cache or peripheral. All core functionality is preserved in eight unchanged RTL files. The separate scan fixture keeps every interface bit controllable or observable; its resources are excluded from the core denominator.'); $report.Add('')
    $report.Add('| Release | MHz | Core physical LUT range | Core FF | Effective uncertainty (ns) | Setup slack (ns) |')
    $report.Add('| --- | ---: | ---: | ---: | ---: | ---: |')
    foreach ($row in $rows) { $report.Add(('| {0} | {1:F3} | {2:N0}–{3:N0} | {4:N0} | {5:F3} | {6:F3} |' -f $row.release, ($row.clock_hz / 1e6), $row.core_lut_min, $row.core_lut_conservative, $row.core_ff, $row.effective_uncertainty_ns, $row.setup_slack_ns)) }
    $report.Add(''); $report.Add('| Release | CoreMark/MHz | CoreMark at target (derived) | CoreMark/LUT (conservative) | CoreMark/MHz/kLUT (conservative) |')
    $report.Add('| --- | ---: | ---: | ---: | ---: |')
    foreach ($row in $rows) { $report.Add(('| {0} | {1:F6} | {2:F3} | {3:F6} | {4:F6} |' -f $row.release, $row.source_coremark_per_mhz, $row.target_clock_derived_coremark, $row.coremark_per_lut_lower, $row.coremark_per_mhz_per_klut_lower)) }
    $report.Add(''); $report.Add('Efficiency uses core-only area with explicitly external cached-system services. The execution counts come from completed 6,000-iteration source simulations, joined to the bare DUT through exact source/configuration/firmware hashes and fresh two-million-edge extraction comparisons. These are service-dependent CPU metrics. They are not a new standalone cacheless-memory benchmark or a full new bare-wrapper run.')
    $report.Add(''); $report.Add('The conservative area denominator assigns every shared or unattributed physical LUT site to the CPU. The lower bound includes only core-exclusive cells and core-exclusive tool-generated constant sites. Distributed RAM sites are already included in LUT totals. All three CPUs retain four APM blocks and no DRM or PLL inside the core.')
    $report.Add(''); $report.Add('Each row passes every checked setup, hold, recovery, removal and pulse-width requirement at both timing corners. Effective uncertainty is reported as observed. It meets or exceeds the 0.150 ns minimum; excess uncertainty is not added to the reported slack.')
    $report.Add(''); $report.Add('| Release | Core-exclusive LUT | Fixture-exclusive LUT | Shared / unattributed LUT | Full physical LUT | Core / fixture FF |')
    $report.Add('| --- | ---: | ---: | ---: | ---: | ---: |')
    foreach ($row in $rows) { $report.Add(('| {0} | {1:N0} | {2:N0} | {3} / {4} | {5:N0} | {6:N0} / {7:N0} |' -f $row.release, $row.core_lut_min, $row.fixture_lut_exclusive, $row.shared_lut_sites, $row.unattributed_lut_slots, $row.whole_fixture_lut, $row.core_ff, $row.fixture_ff)) }
    $report.Add(''); $report.Add('RELEASES.json and each SELECTED_BUILD.json identify exact reports, constraints, tests and source hashes. [Extraction evidence](EXTRACTION_QUALIFICATION.md), [native area methodology](physical-attribution/README.md), and [reproduction instructions](../README.md).')
    $reportPath = [System.IO.Path]::Combine($root, 'analysis', 'RESOURCE_EFFICIENCY.md')
    [System.IO.File]::WriteAllText($reportPath, ($report -join [Environment]::NewLine), $utf8Bom)
    $null = Get-Content -LiteralPath $catalogPath -Raw -Encoding utf8 | ConvertFrom-Json
    $null = [System.IO.File]::ReadAllText($reportPath)
    Write-Output ('BARE_CATALOG_VERIFIED releases=' + $rows.Count + ' native_area_reconciled=true extraction_and_rollback=true')
    Write-Output $catalogPath
    exit 0
} catch { Write-Error $_; exit 1 }
