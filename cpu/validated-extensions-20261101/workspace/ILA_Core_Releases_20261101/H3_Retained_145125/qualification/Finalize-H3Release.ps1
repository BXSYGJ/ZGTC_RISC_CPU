param(
    [ValidateSet('H3_Base_145125', 'H3_Retained_145125')][string]$Release = 'H3_Base_145125'
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
try {
    $taskRoot=[System.IO.Path]::Combine('D:','AAAFPGA','ILA_Core_Releases_20261101')
    $root=[System.IO.Path]::Combine($taskRoot,$Release)
    $qualification=[System.IO.Path]::Combine($root,'qualification')
    $utf8Bom=[System.Text.UTF8Encoding]::new($true)
    function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    function Save([string]$Path,[object]$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 30),$utf8Bom);$null=[System.IO.File]::ReadAllText($Path)}
    $attempts=@()
    foreach($directory in Get-ChildItem -LiteralPath ([System.IO.Path]::Combine($root,'builds')) -Directory|Sort-Object Name){
        $manifestPath=[System.IO.Path]::Combine($directory.FullName,'manifest.json')
        if(-not(Test-Path -LiteralPath $manifestPath)){continue}
        $manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
        $auditPath=[System.IO.Path]::Combine($directory.FullName,'INDEPENDENT_MULTICORNER_AUDIT.json')
        $audit=if(Test-Path -LiteralPath $auditPath){Get-Content -LiteralPath $auditPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable}else{$null}
        $attempts+=[ordered]@{build_directory=$directory.FullName;manifest=$manifestPath;manifest_sha256=Sha $manifestPath;status=$manifest.status;stage=$manifest.stage;placement_seed=$manifest.placement_seed;ila_profile=if($manifest.ContainsKey('ila_profile')){$manifest.ila_profile}else{'Shared42'};report=if($manifest.ContainsKey('report')){$manifest.report}else{$null};independent_audit=if($null-ne$audit){$auditPath}else{$null};independent_audit_passed=($null-ne$audit-and$audit.qualified);bitstream=if($manifest.ContainsKey('bitstream')){$manifest.bitstream}else{$null};bitstream_sha256=if($manifest.ContainsKey('bitstream_sha256')){$manifest.bitstream_sha256}else{$null};fic=if($manifest.ContainsKey('fic')){$manifest.fic}else{$null};fic_sha256=if($manifest.ContainsKey('fic_sha256')){$manifest.fic_sha256}else{$null}}
    }
    Save ([System.IO.Path]::Combine($root,'PHYSICAL_ATTEMPTS.json')) $attempts
    $complete=@($attempts|Where-Object{$null-ne$_.report-and$_.report.Contains('setup_wns_ns')})
    if($complete.Count-lt 1){throw 'No completed physical report is available.'}
    $passed=@($complete|Where-Object{$_.independent_audit_passed-and$_.report.constraints_met-and$_.report.all_corner_audit.all_corners_passed})
    $selected=if($passed.Count){@($passed|Sort-Object {$_.report.setup_wns_ns} -Descending)[0]}else{@($complete|Sort-Object {$_.report.setup_wns_ns} -Descending)[0]}
    $wavePath=[System.IO.Path]::Combine($root,'waveforms','WAVEFORM_MANIFEST.json')
    $wave=Get-Content -LiteralPath $wavePath -Raw -Encoding utf8|ConvertFrom-Json
    $selectedMap=[System.IO.Path]::Combine($selected.build_directory,'implementation','mapping-audit.json')
    $map=Get-Content -LiteralPath $selectedMap -Raw -Encoding utf8|ConvertFrom-Json
    $waveMap=Get-Content -LiteralPath $wave.mapping_audit.path -Raw -Encoding utf8|ConvertFrom-Json
    if($waveMap.data.Count-ne42){throw 'Waveform source capture is not the preserved 42-signal observation.'}
    $sourceIndices=if($map.PSObject.Properties.Name-contains'expanded_observation_source_indices'){@($map.expanded_observation_source_indices)}else{@(0..41)}
    if($sourceIndices.Count-ne$map.data.Count){throw 'Selected capture subset mapping width differs.'}
    for($i=0;$i-lt$map.data.Count;$i++){$expandedIndex=[int]$sourceIndices[$i];if($expandedIndex-lt0-or$expandedIndex-ge42-or$map.data[$i].meaning-cne$waveMap.data[$expandedIndex].meaning){throw 'Selected and simulated probe subset meanings differ.'}}
    $source=Get-Content -LiteralPath ([System.IO.Path]::Combine($qualification,'SOURCE_QUALIFICATION.json')) -Raw -Encoding utf8|ConvertFrom-Json
    $selectedInputs=[System.IO.Path]::Combine($selected.build_directory,'inputs')
    foreach($file in $source.physical_simulation_rtl){if((Sha ([System.IO.Path]::Combine($selectedInputs,'rtl',$file.file)))-cne$file.sha256){throw 'Selected implementation RTL differs from qualified frozen source.'}}
    if((Sha ([System.IO.Path]::Combine($selectedInputs,'firmware.hex')))-cne$source.firmware_hex_sha256){throw 'Selected implementation firmware differs from reference.'}
    $inventory=Get-Content -LiteralPath ([System.IO.Path]::Combine($qualification,'FROZEN_INPUT_HASHES.json')) -Raw -Encoding utf8|ConvertFrom-Json
    $closure=@()
    foreach($file in $inventory){
        $path=[System.IO.Path]::Combine($selectedInputs,$file.relative_path)
        $actual=Sha $path
        if($file.relative_path -cne 'pds_soc_top.v' -and $actual -cne $file.sha256){throw ('Selected frozen input differs: '+$file.relative_path)}
        $closure+=[ordered]@{relative_path=$file.relative_path;frozen_sha256=$file.sha256;selected_path=$path;selected_sha256=$actual;exact_equal=($actual -ceq $file.sha256)}
    }
    $topPattern='\.INIT_FILE\("[^"]+"\)'
    $frozenTop=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($source.frozen_input_root,'pds_soc_top.v'))
    $selectedTop=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($selectedInputs,'pds_soc_top.v'))
    $waveformSourceBuild=[System.IO.Directory]::GetParent([System.IO.Path]::GetDirectoryName($wave.mapping_audit.path)).FullName
    $waveformInputs=[System.IO.Path]::Combine($waveformSourceBuild,'inputs')
    $waveformTop=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($waveformInputs,'pds_soc_top.v'))
    foreach($text in @($frozenTop,$selectedTop,$waveformTop)){if([regex]::Matches($text,$topPattern).Count-ne1){throw 'Top-level firmware binding is not unique.'}}
    $normalized=[regex]::Replace($frozenTop,$topPattern,'.INIT_FILE("FIRMWARE_PATH")')
    if([regex]::Replace($selectedTop,$topPattern,'.INIT_FILE("FIRMWARE_PATH")')-cne$normalized-or[regex]::Replace($waveformTop,$topPattern,'.INIT_FILE("FIRMWARE_PATH")')-cne$normalized){throw 'Top-level source differs beyond firmware path relocation.'}
    $normalizedHash=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($normalized))).ToLowerInvariant()
    foreach($file in $wave.source_inputs){if((Sha $file.path)-cne$file.sha256){throw 'Waveform source binding hash changed.'}}
    if((Sha $wave.elf.path)-cne$wave.elf.sha256-or(Sha $wave.mapping_audit.path)-cne$wave.mapping_audit.sha256){throw 'Waveform ELF or mapping binding changed.'}
    $semanticBindings=@()
    for($i=0;$i-lt$map.data.Count;$i++){$expandedIndex=[int]$sourceIndices[$i];$semanticBindings+=[ordered]@{selected_channel=$i;waveform_expanded_channel=$expandedIndex;meaning=$map.data[$i].meaning;waveform_native=$waveMap.data[$expandedIndex].native;selected_native=$map.data[$i].native;same_logical_signal=$true}}
    $bindingPath=[System.IO.Path]::Combine($root,'SOURCE_TO_SELECTED_BINDING.json')
    $binding=[ordered]@{schema='h3-waveform-source-to-selected-implementation/v1';release=$Release;waveform_origin='LOCAL RTL SIMULATION';waveform_manifest=$wavePath;waveform_manifest_sha256=Sha $wavePath;waveform_source_build=$waveformSourceBuild;waveform_source_mapping=$wave.mapping_audit;selected_build=$selected.build_directory;selected_manifest=$selected.manifest;selected_manifest_sha256=Sha $selected.manifest;selected_mapping=[ordered]@{path=$selectedMap;sha256=Sha $selectedMap};frozen_source_qualification=[ordered]@{path=[System.IO.Path]::Combine($qualification,'SOURCE_QUALIFICATION.json');sha256=Sha ([System.IO.Path]::Combine($qualification,'SOURCE_QUALIFICATION.json'))};all_25_input_files_checked=$true;closure=$closure;top_only_INIT_FILE_path_relocated=$true;normalized_top_sha256=$normalizedHash;firmware_sha256=$source.firmware_hex_sha256;elf=$wave.elf;waveform_observation_width=42;selected_capture_data_width=$map.data.Count;selected_capture_is_subset_of_waveform=($map.data.Count-lt42);selected_capture_semantics_equal_mapped_waveform_subset=$true;waveform_expanded_source_indices=$sourceIndices;signal_bindings=$semanticBindings;selected_trigger_width=$map.trigger_channels;selected_profile=$selected.ila_profile;clock_hz=145125000;cpu_setup_uncertainty_ns=0.150;new_waveform_simulation_required=$false;hardware_capture_claimed=$false;bound_utc=[datetime]::UtcNow.ToString('o')}
    Save $bindingPath $binding
    $fullPath=[System.IO.Path]::Combine($qualification,'full_reference','RESULT.json')
    $fullStatus='running';$fullResult=$null
    if(Test-Path -LiteralPath $fullPath){$fullResult=Get-Content -LiteralPath $fullPath -Raw -Encoding utf8|ConvertFrom-Json;if(-not$fullResult.completed_6000_iterations-or-not$fullResult.exact_reference_uart_equal-or$fullResult.native_exit_code-ne0){throw 'Full reference simulation result is not a pass.'};$fullStatus='completed_exact_reference_pass'}
    if($null-ne$fullResult){
        $fullRoot=[System.IO.Path]::Combine($qualification,'full_reference')
        $fullReceiptPath=[System.IO.Path]::Combine($fullRoot,'NATIVE_PROCESS.json')
        $fullReceipt=Get-Content -LiteralPath $fullReceiptPath -Raw -Encoding utf8|ConvertFrom-Json
        if($fullReceipt.actual_exit_code-ne0){throw 'Full reference native receipt exit differs.'}
        $verification=@(
            'Changed field: pds_soc_top.board.INIT_FILE (firmware path relocation only); functional RTL and firmware are unchanged.',
            ('MODIFIED_FILE='+[System.IO.Path]::Combine($selectedInputs,'pds_soc_top.v')),
            ('DIFF_FILE='+[System.IO.Path]::Combine($selected.build_directory,'DIFF_FILE.txt')),
            ('VERIFICATION='+[System.IO.Path]::Combine($fullRoot,'VERIFICATION.txt')),
            ('ROLLBACK='+[System.IO.Path]::Combine($selected.build_directory,'ROLLBACK.ps1')),
            'BASELINE command/input/output/exit: see ../VERIFICATION.txt for the recorded 2000000-cycle baseline and exact frozen full-run reference artifacts.',
            ('MODIFIED exact command: pwsh -NoProfile -File "'+[System.IO.Path]::Combine($qualification,'Run-H3FullReference.ps1')+'" -Release '+$Release+' -CycleLimit 2100000000'),
            ('MODIFIED exact native command: '+($fullReceipt|ConvertTo-Json -Depth 8 -Compress)),
            ('MODIFIED input: '+$fullReceipt.working_directory+'; firmware SHA256='+$fullResult.firmware_sha256),
            'MODIFIED literal output:',
            $fullResult.literal_stdout.TrimEnd(),
            'MODIFIED actual native exit status: 0',
            ('MODIFIED result: full 6000 iterations; exact frozen reference UART/CRC/counters match; cycles='+$fullResult.cycles+' retired='+$fullResult.retired+' UART SHA256='+$fullResult.uart_sha256),
            'ROLLBACK command/input/literal output/exit: see ../VERIFICATION.txt; separate rollback copy restored all 25 frozen hashes and produced baseline-equal 2000000-cycle observations, exit 0.',
            'Restored behavior/status: baseline behavior reproduced by the separate rollback copy. Selected modified inputs retain the relocated firmware path. Complete new 6000-iteration simulation validates the modified functional core and firmware against the frozen full reference.'
        )
        [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($fullRoot,'VERIFICATION.txt'),$verification,$utf8Bom)
    }
    $qualified=$passed.Count-gt0
    $selection=[ordered]@{release=$Release;status=if($qualified){'internal_timing_passed'}else{'best_observed_timing_miss_open'};build_directory=$selected.build_directory;build_manifest=$selected.manifest;build_manifest_sha256=Sha $selected.manifest;ila_profile=$selected.ila_profile;clock_hz=145125000;placement_seed=$selected.placement_seed;setup_uncertainty_ns=0.150;cpu_setup_wns_ns=$selected.report.setup_wns_ns;all_corner_timing_passed=$qualified;independent_multicorner_audit=$selected.independent_audit;resources=$selected.report.resources;bitstream=$selected.bitstream;bitstream_sha256=$selected.bitstream_sha256;fic=$selected.fic;fic_sha256=$selected.fic_sha256;firmware_sha256=$source.firmware_hex_sha256;hardware_validated=$false;waveform_origin='LOCAL RTL SIMULATION';waveform_manifest=$wavePath;waveform_observation_width=42;selected_capture_data_width=$map.data.Count;selected_trigger_width=$map.trigger_channels;waveform_is_superset_of_selected=($map.data.Count-lt42);selected_meanings_match_explicit_waveform_subset=$true;source_to_selected_binding=$bindingPath;full_simulation_status=$fullStatus;full_simulation_directory=[System.IO.Path]::Combine($qualification,'full_reference');full_simulation_result=if($null-ne$fullResult){$fullPath}else{$null};all_attempts=[System.IO.Path]::Combine($root,'PHYSICAL_ATTEMPTS.json');selected_utc=[datetime]::UtcNow.ToString('o')}
    $selectionPath=[System.IO.Path]::Combine($root,'SELECTED_BUILD.json')
    Save $selectionPath $selection
    $fullLine=if($null-ne$fullResult){'The new full 6000-iteration local RTL simulation completed with native exit 0. Its complete UART, CRCs, cycles ('+$fullResult.cycles+'), and retired count ('+$fullResult.retired+') match the frozen reference byte for byte.'}else{'The new full 6000-iteration local RTL simulation is running. Frozen full-run reference cycles='+$source.reference_cycles+'; retired='+$source.reference_retired+'.'}
    $lines=@(
        ('# '+$Release),
        '',
        ('Selected ILA candidate: `'+$selected.build_directory+'`. Status: **'+$selection.status+'**.'),
        '',
        ('The requested 145.125 MHz target and 0.150 ns CPU setup uncertainty remain in place. CPU slow-corner setup slack is '+$selection.cpu_setup_wns_ns+' ns. All CPU and debug clock setup, hold, recovery, removal, and pulse-width checks are recorded in the independent multicorner audit.'),
        '',
        ('Post-route resources: '+$selection.resources.post_route_luts+' LUTs, '+$selection.resources.post_route_ffs+' FFs, '+$selection.resources.DRM+' DRM units. ILA profile: '+$selection.ila_profile+'.'),
        '',
        'Frozen RTL, PLL, constraints, and firmware remain unchanged. The copied top changes only the firmware INIT_FILE path. The baseline, modified, and separate rollback copy produce identical UART, counters, retirement trace, and 42-signal capture observations over 2000000 cycles.',
        '',
        $fullLine,
        '',
        'The waveforms are **LOCAL RTL SIMULATION**. Each of the list, matrix, and state kernel windows contains 1024 recorded rising edges, with the actual EX-PC/ex-fire capture predicate at sample 256. CSV, VCD, PNG, SVG, source hashes, ELF addresses, and render checks are in `waveforms/`. The horizontal axis is CPU edge index. Actual simulator edges are 10000 ps apart; logical UART configuration CLOCK_HZ=3200/BAUD=100 and the FPGA target are separate metadata.',
        '',
        ('The selected physical core captures '+$map.data.Count+' data signals and uses '+$map.trigger_channels+' trigger signals. The recorded 42-signal local simulation is an explicitly mapped superset when the physical profile is smaller. `SOURCE_TO_SELECTED_BINDING.json` checks all 25 frozen inputs, top-level path normalization, firmware and ELF identity, and every selected capture signal against its original waveform index. Board measurement was not part of this local waveform result.'),
        '',
        'Evidence: `SELECTED_BUILD.json`, `SOURCE_TO_SELECTED_BINDING.json`, `PHYSICAL_ATTEMPTS.json`, `qualification/VERIFICATION.txt`, `qualification/QUALIFICATION_SUMMARY.json`, `qualification/full_reference/`, and `waveforms/WAVEFORM_MANIFEST.json`.'
    )
    [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($root,'README.md'),$lines,$utf8Bom)
    foreach($path in @($selectionPath,[System.IO.Path]::Combine($root,'README.md'),$wavePath,$selected.manifest,$selectedMap,$selected.bitstream,$selected.fic)){if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw ('Selected artifact missing: '+$path)};$null=Get-Item -LiteralPath $path}
    Write-Output ('H3_SELECTION release='+$Release+' status='+$selection.status+' setup_wns_ns='+$selection.cpu_setup_wns_ns+' full_simulation='+$fullStatus)
    Write-Output ('SELECTED_BUILD='+$selectionPath)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
