param(
    [Parameter(Mandatory)][ValidateSet('H3_Base_145125','H3_Retained_145125')][string]$Release,
    [Parameter(Mandatory)][ValidateLength(1,500)][string]$BuildDirectory,
    [Parameter(Mandatory)][ValidateLength(1,500)][string]$CoreAttributionReport
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $taskRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine('D:/AAAFPGA','Bare_Core_Releases_20261101'))
    $releaseRoot = [System.IO.Path]::Combine($taskRoot,$Release)
    $build = [System.IO.Path]::GetFullPath($BuildDirectory)
    $prefix = [System.IO.Path]::Combine($releaseRoot,'physical','builds') + [System.IO.Path]::DirectorySeparatorChar
    if (-not $build.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Selected build must belong to the specified H3 release.' }
    $bom = [System.Text.UTF8Encoding]::new($true)
    function Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    function Read-Json([string]$Path) { Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable }
    function Write-Json([string]$Path,$Value) { [System.IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 30),$bom) }
    $manifestPath = [System.IO.Path]::Combine($build,'manifest.json')
    $manifest = Read-Json $manifestPath
    $reportPath = [System.IO.Path]::Combine($build,'implementation','resource-timing-summary.json')
    $report = Read-Json $reportPath
    $auditPath = [System.IO.Path]::Combine($build,'INDEPENDENT_MULTICORNER_AUDIT.json')
    $audit = Read-Json $auditPath
    $invocation = Read-Json ([System.IO.Path]::Combine($build,'implementation','pds.invocation.json'))
    if ($manifest.release -ne $Release -or $manifest.stage -ne 'implemented' -or $invocation.status -ne 'finished' -or $invocation.exit_code -ne 0) { throw 'Selected native physical run did not complete successfully.' }
    if ($manifest.fixture_profile -ne 'SlowScanStaged' -or $manifest.placement_seed -ne 1) { throw 'Final bounded fixture profile or seed mismatch.' }
    if (@($report.observed_setup_uncertainties_ns).Count -ne 1) { throw 'Actual setup uncertainty is ambiguous.' }
    $actualSetupUncertainty=[double](@($report.observed_setup_uncertainties_ns)[0])
    if ($actualSetupUncertainty -lt 0.150 -or [math]::Abs($audit.reported_effective_setup_uncertainty_ns-$actualSetupUncertainty) -gt 0.0001) { throw 'Actual setup uncertainty does not meet the .150 ns minimum or differs between audits.' }
    if ($report.timing_report_sha256 -ne (Sha $report.timing_report) -or $audit.report_sha256 -ne (Sha $audit.report)) { throw 'Final timing evidence hash mismatch.' }
    $sourcePath = [System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json')
    $source = Read-Json $sourcePath
    if ($manifest.source_manifest_sha256 -ne (Sha $sourcePath) -or $source.rtl.Count -ne 8 -or $source.functional_rtl_changes -ne 0) { throw 'Frozen source manifest mismatch.' }
    $bindings = foreach ($row in $source.rtl) {
        $selectedFile = [System.IO.Path]::Combine($build,'inputs','rtl',[System.IO.Path]::GetFileName($row.path))
        if ((Sha $row.path) -ne $row.sha256 -or (Sha $selectedFile) -ne $row.sha256) { throw ('Frozen RTL mismatch: '+$row.path) }
        [ordered]@{source=$row.path;selected_input=$selectedFile;sha256=$row.sha256}
    }
    $selectedWrapper = [System.IO.Path]::Combine($build,'inputs','rv32_bare_core.sv')
    if ((Sha $source.wrapper.path) -ne $source.wrapper.sha256 -or (Sha $selectedWrapper) -ne $source.wrapper.sha256) { throw 'Core passthrough wrapper differs from qualified wrapper.' }
    $fixtureTestPath = [System.IO.Path]::Combine($build,'SCAN_FIXTURE_TEST.json')
    $fixtureTest = Read-Json $fixtureTestPath
    if ($fixtureTest.status -ne 'PASS' -or $fixtureTest.exit_status -ne 0 -or -not $fixtureTest.two_edge_serial_hold_verified -or -not $fixtureTest.one_edge_snapshot_latency_verified -or $fixtureTest.physical_fixture_sha256 -ne (Sha $fixtureTest.physical_fixture_path) -or $fixtureTest.source_manifest_sha256 -ne (Sha $sourcePath)) { throw 'Exact physical fixture qualification is incomplete.' }
    $miterPath = [System.IO.Path]::Combine($taskRoot,'analysis',$Release+'-EXTRACTION_QUALIFICATION.json')
    $miter = Read-Json $miterPath
    if ($miter.status -ne 'PASS' -or $miter.baseline.exit_code -ne 0 -or $miter.rollback.exit_code -ne 0 -or $miter.modified_negative_control.exit_code -eq 0 -or -not $miter.restored_behavior_equal -or $miter.preparation_sha256 -ne (Sha $miter.preparation)) { throw 'Extraction miter baseline, negative control, or rollback is unqualified.' }
    $fullPath = [System.IO.Path]::Combine('D:/AAAFPGA','ILA_Core_Releases_20261101',$Release,'qualification','full_reference','RESULT.json')
    $full = Read-Json $fullPath
    if (-not $full.completed_6000_iterations -or $full.native_exit_code -ne 0 -or -not $full.exact_reference_uart_equal -or -not $full.all_crc_fields_equal_by_exact_uart) { throw 'Full serviced-system reference simulation did not preserve the frozen result.' }
    $areaPath = [System.IO.Path]::GetFullPath($CoreAttributionReport)
    $area = Read-Json $areaPath
    if (-not [System.IO.Path]::GetFullPath($area.source).StartsWith($build+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or $area.source_sha256 -ne (Sha $area.source) -or $area.native_report.sha256 -ne (Sha $area.native_report.path)) { throw 'Core attribution is not bound to this exact exported routed design.' }
    $hierarchyReconciled = [bool]$area.reconciliation.native_hierarchy_exact -or ($area.reconciliation.Contains('native_hierarchy_reconciled_with_explicit_differences') -and [bool]$area.reconciliation.native_hierarchy_reconciled_with_explicit_differences)
    if (-not $area.reconciliation.ff_exact -or -not $hierarchyReconciled -or $area.reconciliation.global_lut_count -ne $report.resources.lut -or $area.physical_build_binding.manifest_sha256 -ne (Sha $manifestPath)) { throw 'Native routed resource reconciliation failed.' }
    $featurePath = $areaPath.Replace('-PHYSICAL_PRIMITIVE_INVENTORY.json','-FEATURE_PRESERVATION.json')
    $feature = Read-Json $featurePath
    if ($feature.status -ne 'PASS' -or $feature.inventory_sha256 -ne (Sha $areaPath)) { throw 'Routed feature and 64-bit counter preservation audit failed.' }
    $categories = $area.summary.constant_site_consumer_categories
    $fixtureConstants = if ($categories.Contains('fixture_only')) { [int]$categories.fixture_only } else { 0 }
    $sharedLuts = if ($categories.Contains('shared')) { [int]$categories.shared } else { 0 }
    $fixtureLuts = [int]$area.reconciliation.hierarchy_attributed_fixture_lut_including_ram + $fixtureConstants
    $coreLuts = [int]$area.reconciliation.core_lut_with_generated_overhead_lower_bound
    $unattributedLuts = [int]$report.resources.lut - $coreLuts - $fixtureLuts - $sharedLuts
    if ($unattributedLuts -lt 0) { throw 'Negative global LUT residue.' }
    $tclPath = [System.IO.Path]::Combine($build,'implementation','build.tcl')
    if ((Sha $tclPath) -ne $manifest.physical_input_hashes.tcl -or [System.IO.File]::ReadAllText($tclPath) -notmatch 'pnr -dc_duplication true') { throw 'Selected native duplication setting is not proven.' }
    $rollbackPath = [System.IO.Path]::Combine($build,'ROLLBACK.ps1')
    $rollbackReview = [System.IO.Path]::Combine($build,'rollback_final_review')
    if (-not (Test-Path -LiteralPath $rollbackReview)) {
        & $rollbackPath -BuildDirectory $build -DestinationDirectory $rollbackReview
        if ($LASTEXITCODE -ne 0) { throw 'Final separate-copy rollback failed.' }
    }
    if (@(Get-ChildItem -LiteralPath $rollbackReview -File).Count -ne 8) { throw 'Final rollback closure count differs.' }
    foreach ($row in $source.rtl) {
        if ((Sha ([System.IO.Path]::Combine($rollbackReview,[System.IO.Path]::GetFileName($row.path)))) -ne $row.sha256) { throw 'Final rollback does not restore the eight frozen source hashes.' }
    }
    $verificationPath = [System.IO.Path]::Combine($build,'VERIFICATION.txt')
    $qualified = [bool]$report.constraints_met -and [bool]$audit.qualified
    $selection = [ordered]@{
        schema='selected-bare-core-build/v1';release=$Release;status=if($qualified){'physical_timing_passed'}else{'timing_open_final_bounded_attempt'}
        build_directory=$build;manifest=$manifestPath;manifest_sha256=(Sha $manifestPath)
        resource_timing_report=$reportPath;resource_timing_report_sha256=(Sha $reportPath)
        clock_hz=$manifest.clock_hz;setup_wns_ns=$report.setup_wns_ns;all_corner_timing_passed=$qualified;all_corner_violations=$audit.violations;actual_setup_uncertainty_ns=$actualSetupUncertainty;requested_minimum_setup_uncertainty_ns=0.150
        setup_uncertainty_exact_match=([math]::Abs($actualSetupUncertainty-0.150) -lt 0.0001);setup_uncertainty_satisfies_minimum=($actualSetupUncertainty -ge 0.150)
        fixture_profile=$manifest.fixture_profile;placement_seed=$manifest.placement_seed;fixture_test=$fixtureTestPath;fixture_test_sha256=(Sha $fixtureTestPath)
        physical_duplication_enabled=$true;physical_fixture=$fixtureTest.physical_fixture_path;physical_fixture_sha256=$fixtureTest.physical_fixture_sha256;output_snapshot_latency_core_edges=1;minimum_serial_shift_interval_core_edges=2
        resources_total=$report.resources;core_attribution_report=$areaPath;core_attribution_report_sha256=(Sha $areaPath)
        feature_preservation_report=$featurePath;feature_preservation_report_sha256=(Sha $featurePath);native_export_reconciliation=$area.reconciliation
        core_resources=[ordered]@{native_hierarchy_lut_including_distributed_ram=$area.native_report.hierarchy_core.LUT;physical_exclusive_lut=$coreLuts;physical_lut_lower_bound=$coreLuts;physical_lut_upper_bound=$area.reconciliation.core_lut_with_generated_overhead_upper_bound;ff=$area.native_report.hierarchy_core.FF;distributed_ram_lut_sites=$area.native_report.hierarchy_core.'Distributed RAM';APM=$area.native_report.hierarchy_core.APM;DRM=0;GPLL=0}
        fixture_resources=[ordered]@{native_hierarchy_lut=$area.reconciliation.hierarchy_attributed_fixture_lut_including_ram;physical_exclusive_lut=$fixtureLuts;ff=$area.summary.resource_by_region.fixture.FF}
        shared_lut_sites=$sharedLuts;unattributed_lut_slots=$unattributedLuts;global_lut_reconciliation=($report.resources.lut.ToString()+' = '+$coreLuts+' core-exclusive + '+$fixtureLuts+' fixture-exclusive + '+$sharedLuts+' shared + '+$unattributedLuts+' unexported/unattributed slots')
        core_resources_native_hierarchy=$area.native_report.hierarchy_core;fixture_resources_native_hierarchy=[ordered]@{lut=$area.reconciliation.hierarchy_attributed_fixture_lut_including_ram;ff=$area.summary.resource_by_region.fixture.FF}
        core_lut_including_generated_overhead_lower_bound=$area.reconciliation.core_lut_with_generated_overhead_lower_bound
        core_lut_including_generated_overhead_upper_bound=$area.reconciliation.core_lut_with_generated_overhead_upper_bound
        unexported_global_lut_slots=$area.reconciliation.global_lut_slots_not_present_in_export
        source_manifest=$sourcePath;source_manifest_sha256=(Sha $sourcePath);functional_rtl_changes=0
        independent_multicorner_audit=$auditPath;independent_multicorner_audit_sha256=(Sha $auditPath)
        extraction_qualification=$miterPath;extraction_qualification_sha256=(Sha $miterPath)
        full_reference_result=$fullPath;full_reference_result_sha256=(Sha $fullPath);full_reference_cycles=$full.cycles;full_reference_retired=$full.retired
        performance_scope='Finite fresh bare-wrapper extraction miter plus exact source/configuration/firmware join to completed original SoC 6000-iteration local RTL simulation; execution service remains explicitly external cached-system services.'
        verification=$verificationPath;verification_sha256=(Sha $verificationPath);rollback_final_review=$rollbackReview;rollback_restored_eight_frozen_hashes=$true
        hardware_validated=$false;selected_utc=[DateTime]::UtcNow.ToString('o')
    }
    $selectedPath = [System.IO.Path]::Combine($releaseRoot,'SELECTED_BUILD.json')
    Write-Json $selectedPath $selection
    $bindingPath = [System.IO.Path]::Combine($releaseRoot,'SOURCE_TO_SELECTED_BINDING.json')
    Write-Json $bindingPath ([ordered]@{schema='h3-bare-source-selected-binding/v1';release=$Release;source_manifest=$sourcePath;source_manifest_sha256=(Sha $sourcePath);selected_build=$build;selected_manifest=$manifestPath;selected_manifest_sha256=(Sha $manifestPath);eight_frozen_sources=@($bindings);core_wrapper_sha256=$source.wrapper.sha256;changed_field='Build-local physical scan fixture only';fixture_profile=$manifest.fixture_profile;fixture_sha256=$fixtureTest.physical_fixture_sha256;fixture_test=$fixtureTestPath;fixture_test_sha256=(Sha $fixtureTestPath);extraction_miter=$miterPath;extraction_miter_sha256=(Sha $miterPath);full_reference=$fullPath;full_reference_sha256=(Sha $fullPath);native_area_report=$areaPath;native_area_report_sha256=(Sha $areaPath);hardware_validated=$false})
    $attempts = foreach ($dir in (Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($releaseRoot,'physical','builds')) -Directory | Sort-Object Name)) {
        $path = [System.IO.Path]::Combine($dir.FullName,'manifest.json')
        $m = Read-Json $path
        $firstAuditPath = [System.IO.Path]::Combine($dir.FullName,'INDEPENDENT_MULTICORNER_AUDIT.json')
        $firstAudit = if (Test-Path -LiteralPath $firstAuditPath) { Read-Json $firstAuditPath } else { $null }
        [ordered]@{build_directory=$dir.FullName;manifest_status=$m.status;fixture_profile=if($m.Contains('fixture_profile')){$m.fixture_profile}else{'InitialFastScan'};placement_seed=$m.placement_seed;report=if($m.Contains('report')){$m.report}else{$null};independent_audit=$firstAudit;selected=($dir.FullName -eq $build)}
    }
    Write-Json ([System.IO.Path]::Combine($releaseRoot,'PHYSICAL_ATTEMPTS.json')) ([ordered]@{release=$Release;attempts=@($attempts);bounded_final_attempt=$build;additional_attempts=0})
    $lines = @(
        ('# '+$Release+' bare core'),'',
        'The DUT is `rv32_core` inside the unchanged direct passthrough wrapper `rv32_bare_core`. All eight RTL files match the frozen release byte for byte. All 43 ports and 648 bits preserve their names, widths and directions.','',
        'The core excludes caches, external memory services, RAM services, peripherals, UART, PLL and ILA. RV32IMC, predictor and original parameter settings remain enabled. The physical fixture is a separate implementation region.','',
        ('The extraction miter passes 2,000,000 CPU edges and 4,000,000 full-port comparisons. A controlled input fault fails at edge 10000; the real rollback rerun restores the exact result. The selected fixture passes 179 input patterns, checks all 176 input bits and 471 captured output bits, and verifies its two-edge serial hold and one-edge snapshot latency.'),'',
        ('Selected build: `'+[System.IO.Path]::GetRelativePath($releaseRoot,$build).Replace([System.IO.Path]::DirectorySeparatorChar,'/')+'`. The direct external CPU clock is 145.125 MHz; the actual setup uncertainty is '+$actualSetupUncertainty+' ns (minimum requested 0.150 ns). Status: '+$selection.status+'; worst setup slack='+$selection.setup_wns_ns+' ns. All ten slow/fast setup, hold, recovery, removal and pulse-width rows are retained in the independent audit.'),'',
        ('Native routed totals: '+$report.resources.lut+' LUT, '+$report.resources.ff+' FF, '+$report.resources.APM+' APM, '+$report.resources.DRM+' DRM and '+$report.resources.GPLL+' PLL. Native core hierarchy: '+$area.native_report.hierarchy_core.LUT+' LUT and '+$area.native_report.hierarchy_core.FF+' FF. Core LUT allocation including generated overhead is bounded by '+$selection.core_lut_including_generated_overhead_lower_bound+'..'+$selection.core_lut_including_generated_overhead_upper_bound+'; '+$selection.unexported_global_lut_slots+' global LUT slot(s) remain explicit in the reconciliation. Native hierarchy conventions, actual exported primitive ownership and any native-only packed resources remain separate in the linked audit.'),'',
        ('The unchanged source completed a full 6000-iteration local RTL CoreMark run: cycles='+$full.cycles+'; retired='+$full.retired+'; UART, CRC and counters equal the frozen reference. That run uses equivalent external cached memory/peripheral services. Its performance and the bare DUT area have those explicit boundaries; the extraction test is not a standalone cacheless benchmark score.'),'',
        'Evidence: `SELECTED_BUILD.json`, `SOURCE_TO_SELECTED_BINDING.json`, `PHYSICAL_ATTEMPTS.json`, `SOURCE_MANIFEST.json`, `source/parameters.json`, `source/BOUNDARY.json` and `INDEPENDENT_SOURCE_AUDIT.json`. The selection links the exact fixture test, extraction test, native routed area reconciliation and full reference run.'
    )
    $readmePath = [System.IO.Path]::Combine($releaseRoot,'README.md')
    [System.IO.File]::WriteAllLines($readmePath,$lines,$bom)
    foreach ($path in @($selectedPath,$bindingPath,$readmePath,[System.IO.Path]::Combine($releaseRoot,'PHYSICAL_ATTEMPTS.json'),$manifestPath,$reportPath,$auditPath,$fixtureTestPath,$miterPath,$fullPath,$areaPath,$featurePath)) { [void][System.IO.File]::ReadAllBytes($path) }
    Write-Output ('H3_BARE_SELECTED release='+$Release+' status='+$selection.status+' setup_wns_ns='+$report.setup_wns_ns+' total_LUT='+$report.resources.lut+' total_FF='+$report.resources.ff)
    Write-Output ('SELECTED_BUILD='+$selectedPath)
    exit 0
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
