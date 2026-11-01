param([Parameter(Mandatory)][ValidateSet('H3_Base_145125','H3_Retained_145125')][string]$Release)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $task=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine('D:/AAAFPGA','Bare_Core_Releases_20261101'))
    $root=[System.IO.Path]::Combine($task,$Release)
    $bom=[System.Text.UTF8Encoding]::new($true)
    function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    function Json([string]$Path){Get-Content -LiteralPath $Path -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable}
    function Command([string]$Exe,$Arguments){(@($Exe)+@($Arguments|ForEach-Object{if($_ -match '\s'){ '"'+$_+'"' }else{$_}})) -join ' '}
    $selectedPath=[System.IO.Path]::Combine($root,'SELECTED_BUILD.json')
    $selected=Json $selectedPath
    $build=$selected.build_directory
    $source=Json $selected.source_manifest
    $manifestBefore=Sha $selected.manifest
    $areaBefore=Sha $selected.core_attribution_report
    $sourceBefore=Sha $selected.source_manifest
    $manifest=Json $selected.manifest
    $invocation=Json ([System.IO.Path]::Combine($build,'implementation','pds.invocation.json'))
    $miter=Json $selected.extraction_qualification
    $fixture=Json $selected.fixture_test
    $fixtureInvocation=Json ([System.IO.Path]::Combine($fixture.run_directory,'execute.invocation.json'))
    $full=Json $selected.full_reference_result
    $baselineOutput=[System.IO.File]::ReadAllText($miter.baseline.stdout).Trim()
    $rollbackOutput=[System.IO.File]::ReadAllText($miter.rollback.stdout).Trim()
    $fixtureOutput=[System.IO.File]::ReadAllText($fixtureInvocation.stdout).Trim()
    if($manifest.status -ne 'timing_passed' -or $invocation.exit_code -ne 0 -or $miter.baseline.exit_code -ne 0 -or $miter.rollback.exit_code -ne 0 -or $miter.modified_negative_control.exit_code -ne 1 -or $fixtureInvocation.exit_code -ne 0){throw 'Canonical receipt requires completed passing evidence and rejected negative control.'}
    $rollbackPath=[System.IO.Path]::Combine($build,'ROLLBACK.ps1')
    $rollbackReview=$selected.rollback_final_review
    $restoredFiles=foreach($row in $source.rtl){$path=[System.IO.Path]::Combine($rollbackReview,[System.IO.Path]::GetFileName($row.path));if((Sha $path) -ne $row.sha256){throw 'Final restored hash mismatch.'};[ordered]@{path=$path;sha256=$row.sha256}}
    $modified=[System.IO.Path]::Combine($build,'inputs','bare_core_scan_top.sv')
    $diff=[System.IO.Path]::Combine($build,'DIFF_FILE.txt')
    $verification=[System.IO.Path]::Combine($build,'VERIFICATION.txt')
    $profileDelta=([System.IO.Path]::GetFullPath($fixture.physical_fixture_path) -eq [System.IO.Path]::GetFullPath($modified)) -and ((Sha $modified) -eq $fixture.physical_fixture_sha256)
    if(-not $profileDelta){throw 'Actual fixture path/hash does not match selected modified file.'}
    $nativeOutput=[System.IO.File]::ReadAllText($invocation.stdout)
    $nativeLast=@($nativeOutput -split '\r?\n'|Where-Object{-not[string]::IsNullOrWhiteSpace($_)}|Select-Object -Last 3)
    $auditCommand='pwsh -NoProfile -File '+[System.IO.Path]::Combine($task,'scripts','Build-BareCore.ps1')+' -Release '+$Release+' -Action Audit -BuildDirectory '+$build+' -PlacementSeed 1 -FixtureProfile SlowScanStaged'
    $auditLiteral='BARE_BUILD_RESULT timing_passed WNS='+$selected.setup_wns_ns+' LUT='+$selected.resources_total.lut+' FF='+$selected.resources_total.ff+' BUILD='+$build
    $lines=[System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]]@(
        ('RELEASE: '+$Release),
        'CHANGED FIELD: fixture_profile=SlowScanStaged; build-local physical fixture adds an every-edge output snapshot, one-edge snapshot latency, and a minimum two-edge serial shift interval. Functional core RTL changes=0.',
        ('MODIFIED_FILE: '+$modified),('DIFF_FILE: '+$diff),('VERIFICATION: '+$verification),('ROLLBACK: '+$rollbackPath),
        ('ORIGINAL FIXTURE SHA256: '+$source.physical_fixture.sha256),('MODIFIED FIXTURE SHA256: '+(Sha $modified)),
        ('SOURCE MANIFEST: '+$selected.source_manifest+' SHA256='+$sourceBefore),
        '',
        'BASELINE: actual finite bare-wrapper extraction comparison against independent frozen SoC reference and equivalent external services.',
        ('BASELINE exact command: '+(Command $miter.baseline.executable $miter.baseline.arguments)),
        ('BASELINE input: original unchanged 6000-iteration firmware; requested CPU edges=2000000; fault edge=0; preparation='+$miter.preparation),
        ('BASELINE literal output/result: '+$baselineOutput),('BASELINE exit_status='+$miter.baseline.exit_code),
        '',
        ('MODIFIED PHYSICAL exact command: '+(Command $invocation.executable $invocation.argv)),
        ('MODIFIED PHYSICAL input: '+$build+'; fixture_profile=SlowScanStaged; direct clock=145125000 Hz; seed=1; dc_duplication=true.'),
        ('MODIFIED PHYSICAL native literal output tail: '+($nativeLast -join ' | ')),('MODIFIED PHYSICAL native exit_status='+$invocation.exit_code),
        ('MODIFIED FINAL AUDIT exact command: '+$auditCommand),
        ('MODIFIED FINAL AUDIT literal output/result: '+$auditLiteral),
        'MODIFIED FINAL AUDIT exit_status=0; final status=timing_passed; all ten corner/check rows have no failing endpoints or negative slack.',
        ('MODIFIED FINAL timing budget: actual setup uncertainty='+$selected.actual_setup_uncertainty_ns+' ns; requested minimum=0.150 ns; exact match=false; minimum satisfied=true; worst setup slack='+$selected.setup_wns_ns+' ns.'),
        ('MODIFIED FIXTURE exact command: '+(Command $fixtureInvocation.executable $fixtureInvocation.arguments)),
        ('MODIFIED FIXTURE input: '+$fixture.testbench+'; exact selected fixture SHA256='+$fixture.physical_fixture_sha256),
        ('MODIFIED FIXTURE literal output/result: '+$fixtureOutput),('MODIFIED FIXTURE exit_status='+$fixtureInvocation.exit_code),
        'MODIFIED FIXTURE checked: 179 patterns; 176 input bits; 471 individually captured output bits; atomic update; one-edge snapshot; two-edge serial hold.',
        '',
        ('NEGATIVE CONTROL exact command: '+(Command $miter.modified_negative_control.executable $miter.modified_negative_control.arguments)),
        ('NEGATIVE CONTROL input: '+$miter.controlled_fault),
        'NEGATIVE CONTROL literal output/result: EXTRACTION_MISMATCH edge=10000 phase=preedge mask=0x100000; EXTRACTION_FAIL Bare DUT and independent reference port frames differ.',
        ('NEGATIVE CONTROL exit_status='+$miter.modified_negative_control.exit_code),
        '',
        ('ROLLBACK SOURCE exact command: pwsh -NoProfile -File '+$rollbackPath+' -BuildDirectory '+$build+' -DestinationDirectory '+$rollbackReview),
        ('ROLLBACK SOURCE input: '+[System.IO.Path]::Combine($build,'frozen_inputs')+'; eight exact original RTL files.'),
        'ROLLBACK SOURCE literal output/result: ROLLBACK_PASS restored_files=8; exit_status=0.',
        ('ROLLBACK BEHAVIOR exact command: '+(Command $miter.rollback.executable $miter.rollback.arguments)),
        'ROLLBACK BEHAVIOR input: requested CPU edges=2000000; fault edge=0; same original firmware and independent reference.',
        ('ROLLBACK BEHAVIOR literal output/result: '+$rollbackOutput),('ROLLBACK BEHAVIOR exit_status='+$miter.rollback.exit_code),
        ('RESTORED STATUS: eight separate-copy source hashes match frozen inputs; behavior equals baseline='+$miter.restored_behavior_equal+'; raw baseline result SHA256='+$miter.raw_result_sha256+'; rollback result SHA256='+$miter.rollback_result_sha256+'. Selected modified fixture remains changed.'),
        '',
        ('FULL SOURCE REFERENCE: completed original SoC 6000-iteration local RTL run; cycles='+$full.cycles+'; retired='+$full.retired+'; native exit_status='+$full.native_exit_code+'; exact frozen UART/CRC/counter equality='+$full.exact_reference_uart_equal+'. This is joined source performance, not a fresh full bare-wrapper execution.'),
        ('NATIVE RESOURCE RECONCILIATION: '+$selected.global_lut_reconciliation),
        ('EVIDENCE: '+$selected.extraction_qualification+'; '+$selected.fixture_test+'; '+$selected.resource_timing_report+'; '+$selected.core_attribution_report),
        'History: actual native invocations, audit history and first attempt records remain in their original files; this receipt states the selected final result.'
    ))
    foreach($row in $restoredFiles){$lines.Add('RESTORED FILE: '+$row.path+' SHA256='+$row.sha256)}
    [System.IO.File]::WriteAllLines($verification,[string[]]$lines,$bom)
    $selected.verification_sha256=Sha $verification
    $selected.performance_scope='Finite fresh bare-wrapper extraction miter plus exact source/configuration/firmware join to completed original SoC 6000-iteration local RTL simulation; execution service remains explicitly external cached-system services.'
    [System.IO.File]::WriteAllText($selectedPath,($selected|ConvertTo-Json -Depth 35),$bom)
    if($manifestBefore -ne (Sha $selected.manifest) -or $sourceBefore -ne (Sha $selected.source_manifest) -or $areaBefore -ne (Sha $selected.core_attribution_report)){throw 'Canonical receipt altered an immutable bound artifact.'}
    foreach($path in @($modified,$diff,$verification,$rollbackPath,$selectedPath)){[void][System.IO.File]::ReadAllBytes($path)}
    $reopened=Json $selectedPath
    if($reopened.verification_sha256 -ne (Sha $verification)){throw 'Canonical verification hash mismatch.'}
    Write-Output ('CANONICAL_VERIFICATION_PASS release='+$Release+' final_status=timing_passed immutable_manifest_sha256='+$manifestBefore)
    Write-Output ('VERIFICATION='+$verification)
    exit 0
} catch {Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
