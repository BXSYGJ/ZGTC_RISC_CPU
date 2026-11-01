param(
    [Parameter(Mandatory)][ValidateSet('Original_155250','H3_Base_145125','H3_Retained_145125')][string]$Release,
    [ValidateSet('Prepare','Build','Audit')][string]$Action='Build',
    [string]$BuildDirectory,
    [ValidateRange(0,2147483647)][int]$PlacementSeed=2,
    [ValidateSet('Initial','SlowScanStaged')][string]$FixtureProfile='SlowScanStaged'
)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$script:Bom=[System.Text.UTF8Encoding]::new($true)
$script:Plain=[System.Text.UTF8Encoding]::new($false)
$script:Manifest=$null
$script:Mutex=$null
$script:Held=$false
function Save-Json([string]$Path,$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 40),$script:Bom)}
function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Tcl-Path([string]$Path){$p=[System.IO.Path]::GetFullPath($Path).Replace([System.IO.Path]::DirectorySeparatorChar,'/');if($p -match '[{}"$;\r\n]'){throw 'Invalid Tcl path.'};'{'+$p+'}'}
function Save-Manifest{$script:Manifest.updated_utc=[datetime]::UtcNow.ToString('o');Save-Json ([System.IO.Path]::Combine($script:Build,'manifest.json')) $script:Manifest}
function Inventory([string]$Directory){$v=[ordered]@{};foreach($f in Get-ChildItem -LiteralPath $Directory -File -Recurse|Sort-Object FullName){$v[[System.IO.Path]::GetRelativePath($Directory,$f.FullName).Replace([System.IO.Path]::DirectorySeparatorChar,'/')]=Sha $f.FullName};return $v}
function Check-Inputs{
    foreach($relative in $script:Manifest.input_hashes.Keys){$p=[System.IO.Path]::Combine($script:Inputs,$relative);if((Sha $p) -ne $script:Manifest.input_hashes[$relative]){throw ('Build input changed: '+$relative)}}
    if(@(Get-ChildItem -LiteralPath $script:Inputs -File -Recurse).Count -ne $script:Manifest.input_hashes.Count){throw 'Build input file inventory changed.'}
    foreach($row in $script:Manifest.frozen_rtl){if((Sha $row.source) -ne $row.sha256 -or (Sha ([System.IO.Path]::Combine($script:Inputs,'rtl',$row.name))) -ne $row.sha256){throw ('Frozen source identity failed: '+$row.name)}}
}
function Run-Vendor([string]$Executable,[string[]]$Arguments,[string]$Directory){
    $Arguments=@($Arguments|ForEach-Object{$_.Replace([System.IO.Path]::DirectorySeparatorChar,'/')})
    $receiptPath=[System.IO.Path]::Combine($Directory,'pds.invocation.json');$stdout=[System.IO.Path]::Combine($Directory,'pds.stdout.log');$stderr=[System.IO.Path]::Combine($Directory,'pds.stderr.log')
    if(Test-Path -LiteralPath $receiptPath){throw 'This physical invocation already exists. Audit it or prepare another isolated build.'}
    $receipt=[ordered]@{executable=$Executable;executable_sha256=(Sha $Executable);argv=$Arguments;working_directory=$Directory;started_utc=[datetime]::UtcNow.ToString('o');finished_utc=$null;pid=$null;exit_code=$null;status='starting';stdout=$stdout;stderr=$stderr};Save-Json $receiptPath $receipt
    $quoted=@($Arguments|ForEach-Object{if($_ -match '[\r\n"]'){throw 'Invalid process argument.'};if($_ -match '\s'){'"'+$_+'"'}else{$_}})
    $p=Start-Process -FilePath $Executable -ArgumentList $quoted -WorkingDirectory $Directory -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $receipt.pid=$p.Id;$receipt.status='running';Save-Json $receiptPath $receipt
    Write-Host ('PDS_RUNNING pid='+$p.Id+' directory='+$Directory)
    $watch=[System.Diagnostics.Stopwatch]::StartNew()
    while(-not $p.WaitForExit(15000)){Write-Host ('PDS_PROGRESS seconds='+[int]$watch.Elapsed.TotalSeconds);if($watch.Elapsed.TotalHours -gt 3){$receipt.status='monitoring_timeout_process_retained';Save-Json $receiptPath $receipt;throw ('Monitoring deadline exceeded; process remains recorded: '+$p.Id)}}
    $p.Refresh();$receipt.exit_code=$p.ExitCode;$receipt.finished_utc=[datetime]::UtcNow.ToString('o');$receipt.status='finished';Save-Json $receiptPath $receipt
    if($p.ExitCode -ne 0){throw ('PDS exit '+$p.ExitCode+'. Read '+$stderr)}
}
function Corner-Audit([string]$Timing){
    $sections=[regex]::Matches($Timing,'(?ms)^(Setup|Hold|Recovery|Removal|Minimum Pulse Width) Summary\((Slow Corner|Fast Corner)\):\s*(.*?)^={10,}\s*$')
    if($sections.Count -ne 10){throw 'All ten slow/fast setup, hold, recovery, removal, and pulse-width summaries are required.'}
    $tables=[System.Collections.Generic.List[object]]::new();$passed=$true
    foreach($section in $sections){$rows=[regex]::Matches($section.Groups[3].Value,'(?m)^(.*?)\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$');if($rows.Count -lt 1){throw 'Timing summary table is empty.'};$entries=[System.Collections.Generic.List[object]]::new();foreach($row in $rows){$slack=[double]::Parse($row.Groups[2].Value,[Globalization.CultureInfo]::InvariantCulture);$tns=[double]::Parse($row.Groups[3].Value,[Globalization.CultureInfo]::InvariantCulture);$ok=$slack -ge 0 -and [math]::Abs($tns) -lt 0.0001 -and [int]$row.Groups[4].Value -eq 0;$passed=$passed -and $ok;$entries.Add([ordered]@{clock_columns=$row.Groups[1].Value.Trim();slack_ns=$slack;total_negative_slack_ns=$tns;failing_endpoints=[int]$row.Groups[4].Value;total_endpoints=[int]$row.Groups[5].Value;passed=$ok})};$tables.Add([ordered]@{check=$section.Groups[1].Value;corner=$section.Groups[2].Value;rows=$entries.ToArray()})}
    return [ordered]@{all_corners_passed=$passed;summary_tables_checked=10;tables=$tables.ToArray()}
}
function Resource-Totals([string]$Text){
    $resources=[ordered]@{};$lut=0;$ff=0
    foreach($block in @('CLMA','CLMS')){$m=[regex]::Match($Text,'\| Use of '+$block+'\s+\|[^\n]+\n\|\s+FF\s+\|\s*(\d+)[^\n]+\n\|\s+LUT\s+\|\s*(\d+)');if(-not $m.Success){throw ('Missing native resource block: '+$block)};$resources[$block]=[ordered]@{ff=[int]$m.Groups[1].Value;lut=[int]$m.Groups[2].Value};$ff+=[int]$m.Groups[1].Value;$lut+=[int]$m.Groups[2].Value}
    foreach($name in @('APM','DRM','GPLL','IO')){$m=[regex]::Match($Text,'\| Use of '+$name+'\s+\|\s*([0-9.]+)\s*\|');if(-not$m.Success){throw ('Missing native resource total: '+$name)};$resources[$name]=[double]::Parse($m.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)}
    $resources.lut=$lut;$resources.ff=$ff;return $resources
}
function Boundary-Presence([string]$Directory,$Boundary){
    $path=[System.IO.Path]::Combine($Directory,'synthesize','bare_core_scan_top_syn.vm');$vm=[System.IO.File]::ReadAllText($path)
    $modules=[System.Collections.Generic.List[object]]::new()
    foreach($name in @('rv32_bare_core','rv32_core')){
        $m=[regex]::Matches($vm,'(?ms)^\(\* PAP_HIER="fixed" \*\)module '+$name+'\s*\((.*?)\);')
        if($m.Count -ne 1){throw ('Fixed synthesis boundary missing or ambiguous: '+$name)}
        $ports=[ordered]@{}
        foreach($p in [regex]::Matches($m[0].Groups[1].Value,'(?m)^\s*(input|output)\s*(?:\[(\d+):(\d+)\])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$')){$width=if($p.Groups[2].Success){[int]$p.Groups[2].Value-[int]$p.Groups[3].Value+1}else{1};$ports[$p.Groups[4].Value]=[ordered]@{direction=$p.Groups[1].Value;width=$width}}
        if($ports.Count -ne $Boundary.ports.Count){throw ('Synthesis changed core port count: '+$name)}
        foreach($p in $Boundary.ports){if(-not$ports.Contains($p.name) -or $ports[$p.name].width -ne $p.width -or $ports[$p.name].direction -ne $p.direction){throw ('Synthesis changed a core boundary port: '+$name+'.'+$p.name)}}
        $modules.Add([ordered]@{module=$name;fixed_hierarchy=$true;port_count=$ports.Count;port_bits=[int](($ports.Values.width|Measure-Object -Sum).Sum);every_frozen_port_preserved=$true})
    }
    $mapPath=[System.IO.Path]::Combine($Directory,'device_map','bare_core_scan_top.dmr');$map=[System.IO.File]::ReadAllText($mapPath);$start=$map.IndexOf('Device Utilization Summary Of Each Module:');if($start -lt 0){throw 'Native detailed per-module resource table missing.'};$rows=$map.Substring($start) -split '\r?\n';$columns=$null;$entries=[ordered]@{}
    foreach($line in $rows){if($line -notmatch '^\|'){continue};$cells=@(($line -split '\|')|Select-Object -Skip 1|ForEach-Object{$_.Trim()});if($cells[0] -eq 'Module Inst Name'){$columns=$cells;continue};if($null -eq $columns){continue};$label=$cells[0];if($label -notin @('bare_core_scan_top','+ core_boundary','+ dut')){continue};$values=[ordered]@{};for($i=1;$i -lt $columns.Count;$i++){if($columns[$i] -and $cells[$i]){$values[$columns[$i]]=[double]::Parse($cells[$i],[Globalization.CultureInfo]::InvariantCulture)}};$entries[$label]=$values}
    if($entries.Count -ne 3){throw 'Detailed native resource rows do not retain both fixed core boundaries.'}
    foreach($column in $entries['+ dut'].Keys){if($entries['+ dut'][$column] -ne $entries['+ core_boundary'][$column]){throw 'Passthrough wrapper unexpectedly has mapped logic.'}}
    $expectedScanFf=2*[int]$Boundary.scan_controlled_input_bits+[int]$Boundary.individually_captured_output_bits;if($Boundary.Contains('fixture_profile') -and $Boundary.fixture_profile -eq 'SlowScanStaged'){$expectedScanFf+=[int]$Boundary.individually_captured_output_bits+1};$actualScanFf=[int]($entries['bare_core_scan_top'].FF-$entries['+ dut'].FF)
    if($actualScanFf -ne $expectedScanFf){throw 'Native map scan-register count differs from the fully observable fixture contract.'}
    if($entries['+ dut'].DRM -ne 0 -or $entries['+ dut'].GPLL -ne 0 -or $entries['+ dut'].SCANCHAIN -ne 0 -or $entries['+ dut'].IO -ne 0){throw 'The mapped bare core contains excluded RAM, PLL, JTAG, or I/O hardware.'}
    return [ordered]@{synthesized_netlist=$path;synthesized_netlist_sha256=(Sha $path);fixed_modules=$modules.ToArray();native_detailed_map=$mapPath;native_detailed_map_sha256=(Sha $mapPath);map_stage_resources=$entries;scan_fixture_ff_expected=$expectedScanFf;scan_fixture_ff_observed_at_map=$actualScanFf;map_stage_is_not_post_route_attribution=$true}
}
function Native-Inventory([string]$Path){
    $text=[System.IO.File]::ReadAllText($Path);$instances=[regex]::Matches($text,'(?m)^Inst\r?\n([^;\r\n]+);([^\r\n]+)')
    if($instances.Count -lt 100){throw 'Routed native primitive inventory is unexpectedly small.'}
    $rows=[System.Collections.Generic.List[object]]::new();$counts=[ordered]@{core=[ordered]@{};fixture=[ordered]@{};infrastructure=[ordered]@{};unattributed=[ordered]@{}}
    foreach($inst in $instances){$name=$inst.Groups[1].Value;$type=$inst.Groups[2].Value;$partition=if($name.StartsWith('core_boundary/dut/')){'core'}elseif($name.StartsWith('core_boundary/')){'unattributed'}elseif($name -match '^(input_shift|active_inputs|output_shift|N\d+|_N\d+)'){'fixture'}elseif($type -match '^gop(VCC|GND|CLK|HCKB|BKCL|CCS|IBUF|OBUF|IOL)'){'infrastructure'}else{'unattributed'};if(-not$counts[$partition].Contains($type)){$counts[$partition][$type]=0};$counts[$partition][$type]++;$rows.Add([ordered]@{name=$name;primitive=$type;partition=$partition})}
    $core=@($rows|Where-Object {$_.partition -eq 'core'});if($core.Count -lt 100){throw 'Fixed core hierarchy is absent from the routed primitive inventory.'}
    $forbidden=@($rows|Where-Object {$_.partition -eq 'core' -and $_.primitive -match '^gop(DRM|GPLL|SCANCHAIN)'});if($forbidden.Count){throw 'Bare core unexpectedly contains block RAM, PLL, or JTAG scan hardware.'}
    $sum=0;foreach($group in $counts.Keys){foreach($n in $counts[$group].Values){$sum+=$n}};if($sum -ne $instances.Count){throw 'Native primitive partitions do not reconcile.'}
    return [ordered]@{path=$Path;sha256=(Sha $Path);primitive_instances=$instances.Count;partitioned_instances=$sum;all_primitive_instances_reconciled=$true;counts_by_partition=$counts;instances=$rows.ToArray();core_prefix='core_boundary/dut/';resource_units='Routed packed primitive instances. LUT and FF weights are reconciled separately against the native utilization report.'}
}
try{
    $task=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'));$releaseRoot=[System.IO.Path]::Combine($task,$Release);$source=[System.IO.Path]::Combine($releaseRoot,'source');$sourceManifestPath=[System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json')
    $sourceManifest=Get-Content -LiteralPath $sourceManifestPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    if($sourceManifest.release -ne $Release -or $sourceManifest.functional_rtl_changes -ne 0){throw 'Source manifest does not identify an unchanged frozen release.'}
    foreach($row in $sourceManifest.rtl){if((Sha $row.path) -ne $row.sha256 -or (Sha $row.source) -ne $row.sha256){throw ('Source identity mismatch: '+$row.name)}}
    foreach($key in @('wrapper','physical_fixture','boundary')){if((Sha $sourceManifest[$key].path) -ne $sourceManifest[$key].sha256){throw ('Prepared boundary changed: '+$key)}}
    $boundary=Get-Content -LiteralPath $sourceManifest.boundary.path -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    if($boundary.scan_controlled_input_bits -ne 176 -or $boundary.all_port_bits -ne $(if($Release -eq 'Original_155250'){616}else{648})){throw 'Bare boundary width mismatch.'}
    foreach($direction in @('input','output')){$bits=if($direction -eq 'input'){176}else{[int]$boundary.individually_captured_output_bits};$mapping=if($direction -eq 'input'){$boundary.input_mapping}else{$boundary.output_mapping};$covered=[bool[]]::new($bits);foreach($row in $mapping){if($row.width -ne $row.msb-$row.lsb+1){throw 'Invalid scan port width.'};foreach($bit in $row.lsb..$row.msb){if($bit -lt 0 -or $bit -ge $bits -or $covered[$bit]){throw 'Overlapping or out-of-range scan boundary.'};$covered[$bit]=$true}};if(@($covered|Where-Object{-not$_}).Count){throw 'Scan boundary omits core bits.'}}
    if([string]::IsNullOrWhiteSpace($BuildDirectory)){
        if($Action -eq 'Audit'){throw 'Audit requires an explicit BuildDirectory.'}
        $id=[datetime]::Now.ToString('yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8);$BuildDirectory=[System.IO.Path]::Combine($releaseRoot,'physical','builds',$id)
    }
    $script:Build=[System.IO.Path]::GetFullPath($BuildDirectory);$allowed=[System.IO.Path]::Combine($releaseRoot,'physical','builds')+[System.IO.Path]::DirectorySeparatorChar
    if(-not$script:Build.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'BuildDirectory must be inside this release physical/builds directory.'}
    [void][System.IO.Directory]::CreateDirectory($script:Build);$script:Inputs=[System.IO.Path]::Combine($script:Build,'inputs');$manifestPath=[System.IO.Path]::Combine($script:Build,'manifest.json');$implementation=[System.IO.Path]::Combine($script:Build,'implementation')
    if(-not(Test-Path -LiteralPath $manifestPath)){
        Copy-Item -LiteralPath $source -Destination $script:Inputs -Recurse
        if($FixtureProfile -eq 'SlowScanStaged'){
            $fixturePath=[System.IO.Path]::Combine($script:Inputs,'bare_core_scan_top.sv');$fixture=[System.IO.File]::ReadAllText($fixturePath)
            $fixture=$fixture.Replace('    wire [OUTPUT_BITS-1:0] core_outputs;','    wire [OUTPUT_BITS-1:0] core_outputs;'+[Environment]::NewLine+'    (* syn_preserve=1 *) reg [OUTPUT_BITS-1:0] output_snapshot;'+[Environment]::NewLine+'    (* syn_preserve=1 *) reg scan_phase;')
            $fixture=$fixture.Replace('if(!fixture_reset_n) begin input_shift<=0; active_inputs<=0; output_shift<=0; end','if(!fixture_reset_n) begin input_shift<=0; active_inputs<=0; output_shift<=0; output_snapshot<=0; scan_phase<=0; end')
            $fixture=$fixture.Replace('            if(scan_shift) input_shift','            output_snapshot<=core_outputs;'+[Environment]::NewLine+'            scan_phase<=~scan_phase;'+[Environment]::NewLine+'            if(!scan_phase) begin'+[Environment]::NewLine+'            if(scan_shift) input_shift')
            $fixture=$fixture.Replace('if(scan_capture) output_shift<=core_outputs;','if(scan_capture) output_shift<=output_snapshot;')
            $fixture=$fixture.Replace('        end'+[Environment]::NewLine+'    end','            end'+[Environment]::NewLine+'        end'+[Environment]::NewLine+'    end')
            [System.IO.File]::WriteAllText($fixturePath,$fixture,$script:Plain)
            $boundary.fixture_profile='SlowScanStaged';$boundary.output_snapshot_latency_core_edges=1;$boundary.minimum_serial_shift_interval_core_edges=2;$boundary.scan_phase_reset=0;$boundary.scan_operations_acceptance='scan_shift, scan_update, and scan_capture act only when the pre-edge scan_phase is zero. output_snapshot captures every core edge.'
            Save-Json ([System.IO.Path]::Combine($script:Inputs,'BOUNDARY.json')) $boundary
        }
        $frozen=[System.IO.Path]::Combine($script:Build,'frozen_inputs');[void][System.IO.Directory]::CreateDirectory($frozen);foreach($row in $sourceManifest.rtl){Copy-Item -LiteralPath $row.source -Destination ([System.IO.Path]::Combine($frozen,$row.name))}
        $rollbackScript=[System.IO.Path]::Combine($PSScriptRoot,'Restore-BareCoreInputs.ps1');Copy-Item -LiteralPath $rollbackScript -Destination ([System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1'))
        $rollbackTest=[System.IO.Path]::Combine($script:Build,'rollback_test');& ([System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1')) -BuildDirectory $script:Build -DestinationDirectory $rollbackTest
        if($LASTEXITCODE -ne 0){throw 'Rollback execution failed.'}
        $before=Inventory $frozen;$restored=Inventory $rollbackTest;if(($before|ConvertTo-Json -Compress) -ne ($restored|ConvertTo-Json -Compress)){throw 'Rollback inventory differs from all eight frozen sources.'}
        $script:Manifest=[ordered]@{schema='bare-core-physical/v1';release=$Release;status='prepared';stage='prepared';created_utc=[datetime]::UtcNow.ToString('o');updated_utc=$null;clock_hz=[long]$sourceManifest.configured_clock_hz;setup_uncertainty_ns=0.150;hold_uncertainty_ns=if($FixtureProfile -eq 'Initial'){0.050}else{0.150};placement_seed=$PlacementSeed;fixture_profile=$FixtureProfile;source_manifest=$sourceManifestPath;source_manifest_sha256=(Sha $sourceManifestPath);frozen_rtl=$sourceManifest.rtl;parameters=$sourceManifest.parameters;boundary=$boundary;input_hashes=(Inventory $script:Inputs);rollback_test=[ordered]@{path=$rollbackTest;restored_eight_frozen_hashes=$true};functional_rtl_changes=0;clocking='Direct physical clock pin, no PLL';timing_scope='Physical scan fixture with fixed core boundary. No virtual I/O.';hardware_validated=$false}
        [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($script:Build,'DIFF_FILE.txt'),[string[]]@('CHANGED FIELD: Added standalone rv32_bare_core passthrough and bare_core_scan_top physical scan fixture.','Unchanged functional RTL: all eight frozen source file SHA256 values.','DUT hierarchy: core_boundary/dut; no cache, memory system, RAM service, peripheral, PLL, or ILA.',('Scan-controlled core input bits excluding clock: '+$boundary.scan_controlled_input_bits),('Individually captured core output bits: '+$boundary.individually_captured_output_bits)),$script:Bom)
        [System.IO.File]::WriteAllLines([System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),[string[]]@('BASELINE: frozen eight-file closure; every file SHA256 matches SOURCE_MANIFEST.json.','MODIFIED: unchanged closure plus passive passthrough and physical serial scan fixture.','ROLLBACK command: pwsh -NoProfile -File ROLLBACK.ps1 -BuildDirectory BUILD -DestinationDirectory rollback_test','ROLLBACK input: frozen_inputs (eight exact frozen RTL files).','ROLLBACK literal output/result: ROLLBACK_PASS restored_files=8; exit_status=0.','Restored status: rollback_test contains the exact eight frozen RTL files; modified inputs retain both wrappers.'),$script:Bom)
        Save-Manifest
    }else{$script:Manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable;if($script:Manifest.release -ne $Release){throw 'Build release mismatch.'};$PlacementSeed=[int]$script:Manifest.placement_seed;$FixtureProfile=if($script:Manifest.Contains('fixture_profile')){$script:Manifest.fixture_profile}else{'Initial'}}
    Check-Inputs
    [void][System.IO.Directory]::CreateDirectory($implementation)
    $fdcPath=[System.IO.Path]::Combine($script:Build,'bare_core.fdc');$period=(1e9/$script:Manifest.clock_hz).ToString('F6',[Globalization.CultureInfo]::InvariantCulture);$half=(0.5e9/$script:Manifest.clock_hz).ToString('F6',[Globalization.CultureInfo]::InvariantCulture)
    $fdc=[System.Collections.Generic.List[string]]::new();$fdc.AddRange([string[]]@(('create_clock -name {core_clk} [get_ports {clk}] -period {'+$period+'} -waveform {0.000000 '+$half+'}'),'set_clock_uncertainty -setup 0.150 [get_clocks {core_clk}]','set_clock_uncertainty -hold 0.050 [get_clocks {core_clk}]','set_input_delay -clock {core_clk} -max 0.500 [get_ports {fixture_reset_n scan_in scan_shift scan_update scan_capture}]','set_input_delay -clock {core_clk} -min 0.000 [get_ports {fixture_reset_n scan_in scan_shift scan_update scan_capture}]','set_output_delay -clock {core_clk} -max 0.500 [get_ports {scan_out}]','set_output_delay -clock {core_clk} -min 0.000 [get_ports {scan_out}]','define_attribute {v:rv32_bare_core} {syn_hier} {fixed}','define_attribute {v:rv32_core} {syn_hier} {fixed}'))
    if($FixtureProfile -eq 'SlowScanStaged'){
        $fdc=[System.Collections.Generic.List[string]]::new();$fdc.AddRange([string[]]@(('create_clock -name {core_clk} [get_ports {clk}] -period {'+$period+'} -waveform {0.000000 '+$half+'}'),'set_clock_uncertainty 0.150 [get_clocks {core_clk}]','set_input_delay -clock {core_clk} -clock_fall -max 0.500 [get_ports {fixture_reset_n scan_in scan_shift scan_update scan_capture}]','set_input_delay -clock {core_clk} -clock_fall -min 0.000 [get_ports {fixture_reset_n scan_in scan_shift scan_update scan_capture}]','set_output_delay -clock {core_clk} -max 0.500 [get_ports {scan_out}]','set_output_delay -clock {core_clk} -min 0.000 [get_ports {scan_out}]','set_multicycle_path 2 -setup -to [get_ports {scan_out}]','set_multicycle_path 1 -hold -to [get_ports {scan_out}]','define_attribute {v:rv32_bare_core} {syn_hier} {fixed}','define_attribute {v:rv32_core} {syn_hier} {fixed}'))
    }
    $pins=[ordered]@{clk='D18';fixture_reset_n='C22';scan_in='C23';scan_shift='A20';scan_update='C18';scan_capture='C19';scan_out='E18'}
    foreach($name in $pins.Keys){$dir=if($name -eq 'scan_out'){'OUTPUT'}else{'INPUT'};$fdc.Add('define_attribute {p:'+$name+'} {PAP_IO_DIRECTION} {'+$dir+'}');$fdc.Add('define_attribute {p:'+$name+'} {PAP_IO_LOC} {'+$pins[$name]+'}');$fdc.Add('define_attribute {p:'+$name+'} {PAP_IO_VCCIO} {3.3}');$fdc.Add('define_attribute {p:'+$name+'} {PAP_IO_STANDARD} {LVCMOS33}');$fdc.Add('define_attribute {p:'+$name+'} {PAP_IO_NONE} {TRUE}')};$fdc.Add('define_attribute {p:scan_out} {PAP_IO_DRIVE} {8}');$fdc.Add('define_attribute {p:scan_out} {PAP_IO_SLEW} {SLOW}')
    $tclPath=[System.IO.Path]::Combine($implementation,'build.tcl');$tcl=[System.Collections.Generic.List[string]]::new();foreach($row in $script:Manifest.frozen_rtl){$tcl.Add('add_design '+(Tcl-Path ([System.IO.Path]::Combine($script:Inputs,'rtl',$row.name))))};foreach($name in @('rv32_bare_core.sv','bare_core_scan_top.sv')){$tcl.Add('add_design '+(Tcl-Path ([System.IO.Path]::Combine($script:Inputs,$name))))}
    $duplication=if($FixtureProfile -eq 'SlowScanStaged'){'true'}else{'false'}
    $tcl.AddRange([string[]]@(('add_constraint '+(Tcl-Path $fdcPath)),'set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676','compile -system_verilog -top_module bare_core_scan_top','synthesize -ads -selected_syn_tool_opt 2','dev_map -detail',('pnr -dc_duplication '+$duplication+' -plc_decongestion 0 -gplace_seed '+$PlacementSeed+' -logic_optimize_lut6d_combing_strategy 3'),'report_timing','gen_netlist'))
    if($Action -ne 'Audit'){[System.IO.File]::WriteAllLines($fdcPath,[string[]]$fdc,$script:Plain);[System.IO.File]::WriteAllLines($tclPath,[string[]]$tcl,$script:Plain);$script:Manifest.physical_input_hashes=[ordered]@{fdc=(Sha $fdcPath);tcl=(Sha $tclPath)};Save-Manifest}
    if($Action -eq 'Prepare'){foreach($path in @($fdcPath,$tclPath,$manifestPath,[System.IO.Path]::Combine($script:Build,'DIFF_FILE.txt'),[System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),[System.IO.Path]::Combine($script:Build,'ROLLBACK.ps1'))){[void][System.IO.File]::ReadAllBytes($path)};Write-Output ('BARE_PHYSICAL_PREPARED '+$script:Build);exit 0}
    if($Action -eq 'Build'){
        if($FixtureProfile -eq 'SlowScanStaged'){$testPath=[System.IO.Path]::Combine($script:Build,'SCAN_FIXTURE_TEST.json');$test=Get-Content -LiteralPath $testPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable;if($test.status -ne 'PASS' -or -not$test.two_edge_serial_hold_verified -or -not$test.one_edge_snapshot_latency_verified -or $test.physical_fixture_sha256 -ne (Sha ([System.IO.Path]::Combine($script:Inputs,'bare_core_scan_top.sv')))){throw 'The exact staged build fixture must pass its dynamic phase, latency, and scan test before PDS.'}}
        $script:Manifest.status='waiting_for_vendor_mutex';if($script:Manifest.Contains('error')){$script:Manifest.Remove('error')};Save-Manifest
        $script:Mutex=[System.Threading.Mutex]::new($false,'AAAFPGA_PDS2022_MinimalILA');while(-not$script:Held){try{$script:Held=$script:Mutex.WaitOne(15000)}catch [System.Threading.AbandonedMutexException]{$script:Held=$true};if(-not$script:Held){Write-Host ('WAITING_PDS '+[datetime]::UtcNow.ToString('o'))}}
        $active=@(Get-Process -Name pds_shell,cdt_ins -ErrorAction SilentlyContinue);if($active.Count){throw ('An external PDS process is active. No processes were stopped. PIDs='+($active.Id -join ','))}
        $pds=[System.IO.Path]::Combine('D:/','PDS_2022.2-SP6.4','bin','pds_shell.exe');if(-not(Test-Path -LiteralPath $pds)){throw 'Installed PDS executable missing.'};if([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)){$env:PANGO_LICENSE_FILE=[Environment]::GetEnvironmentVariable('PANGO_LICENSE_FILE','User')};if([string]::IsNullOrWhiteSpace($env:PANGO_LICENSE_FILE)){throw 'PANGO_LICENSE_FILE is not configured.'}
        $script:Manifest.status='running';$script:Manifest.stage='vendor_started';Save-Manifest
        Run-Vendor $pds @('-file',$tclPath,'-work_dir',$implementation,'-project_name','bare_core') $implementation
    }
    Check-Inputs
    if((Sha $fdcPath) -ne $script:Manifest.physical_input_hashes.fdc -or (Sha $tclPath) -ne $script:Manifest.physical_input_hashes.tcl){throw 'Physical constraints or Tcl changed.'}
    $timingPath=[System.IO.Path]::Combine($implementation,'report_timing','bare_core_scan_top.rtr');$nativePath=[System.IO.Path]::Combine($implementation,'place_route','bare_core_scan_top_pnr.netlist');$logPath=[System.IO.Path]::Combine($implementation,'run.log')
    $invocation=Get-Content -LiteralPath ([System.IO.Path]::Combine($implementation,'pds.invocation.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    if($invocation.exit_code -ne 0 -or $invocation.status -ne 'finished'){throw 'Physical vendor completion is unproven.'}
    $start=if($invocation.started_utc -is [datetime]){$invocation.started_utc.ToUniversalTime()}else{[datetime]::Parse([string]$invocation.started_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()};$end=if($invocation.finished_utc -is [datetime]){$invocation.finished_utc.ToUniversalTime()}else{[datetime]::Parse([string]$invocation.finished_utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()}
    foreach($path in @($timingPath,$nativePath,$logPath)){$f=Get-Item -LiteralPath $path;if($f.Length -lt 1 -or $f.LastWriteTimeUtc -lt $start.AddSeconds(-2) -or $f.LastWriteTimeUtc -gt $end.AddSeconds(2)){throw ('Empty or stale physical output: '+$path)}}
    $timing=[System.IO.File]::ReadAllText($timingPath);$log=[System.IO.File]::ReadAllText($logPath)
    if($log -notmatch 'Executing : dev_map -detail successfully\.' -or $log -notmatch 'Executing : gen_netlist successfully\.') {throw 'Native detailed mapping or post-route simulation netlist export did not complete.'}
    $clocks=[regex]::Matches($timing,'(?m)^\s*core_clk\s+([0-9.]+)\s+\{[^}]+\}\s+Declared\s+(\d+)');if($clocks.Count -ne 1 -or [math]::Abs([double]::Parse($clocks[0].Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)-1e9/$script:Manifest.clock_hz) -gt 0.005){throw 'Physical direct CPU clock mismatch.'}
    if($timing -match '(?m)^\s*DebugCore_' -or $timing -match 'Virtual I/O'){throw 'Bare timing unexpectedly contains ILA or virtual I/O.'}
    $setupPaths=@($timing -split '(?m)(?=^Startpoint\s*:)'|Where-Object{$_ -match '(?m)^Path Group\s*:\s*core_clk\s*$' -and $_ -match '(?m)^Path Type\s*:\s*max ' -and $_ -match '\bSetup time'});$uncertainties=@($setupPaths|ForEach-Object{[regex]::Matches($_,'clock uncertainty\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s*\n\s*Setup time')}|ForEach-Object{[double]::Parse($_.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture)});if($uncertainties.Count -lt 2 -or $uncertainties.Count -ne $setupPaths.Count){throw 'Detailed CPU setup uncertainty is missing.'};$uncertaintyCorrect=@($uncertainties|Where-Object{[math]::Abs($_+0.150) -gt 0.0001}).Count -eq 0;$uncertaintyMinimum=@($uncertainties|Where-Object{$_ -gt -0.1499}).Count -eq 0
    $corners=Corner-Audit $timing;$summary=[regex]::Match($timing,'Design Summary\s*:\s*([^\r\n]+)').Groups[1].Value.Trim();$totals=Resource-Totals (($log -split 'Device Utilization Summary :')[-1]);$presence=Boundary-Presence $implementation $script:Manifest.boundary;Save-Json ([System.IO.Path]::Combine($implementation,'boundary-presence-audit.json')) $presence;$native=Native-Inventory $nativePath;Save-Json ([System.IO.Path]::Combine($implementation,'routed-primitive-inventory.json')) $native
    $setupRows=@($corners.tables|Where-Object{$_.check -eq 'Setup'}|ForEach-Object{$_.rows});$wns=($setupRows.slack_ns|Measure-Object -Minimum).Minimum
    $report=[ordered]@{clock_hz=$script:Manifest.clock_hz;clock_period_ns=[double]$period;requested_minimum_setup_uncertainty_ns=0.150;requested_setup_uncertainty_ns=0.150;observed_setup_uncertainties_ns=@($uncertainties|ForEach-Object{[math]::Abs($_)}|Sort-Object -Unique);setup_uncertainty_matches_request=$uncertaintyCorrect;setup_uncertainty_exact_match=$uncertaintyCorrect;setup_uncertainty_satisfies_minimum=$uncertaintyMinimum;setup_uncertainty_note='Actual deductions are read from the native report. A passing route at a larger setup uncertainty satisfies the requested minimum budget; it is not relabeled as an exact match.';setup_uncertainty_paths_checked=$uncertainties.Count;clock_loads=[int]$clocks[0].Groups[2].Value;setup_wns_ns=$wns;timing_summary=$summary;constraints_met=($summary -eq 'All Constraints Met.' -and $corners.all_corners_passed -and $uncertaintyMinimum);all_corner_audit=$corners;resources=$totals;routed_primitive_inventory=[ordered]@{path=[System.IO.Path]::Combine($implementation,'routed-primitive-inventory.json');sha256=(Sha ([System.IO.Path]::Combine($implementation,'routed-primitive-inventory.json')));primitive_instances=$native.primitive_instances;all_primitive_instances_reconciled=$native.all_primitive_instances_reconciled};area_attribution_status='Packed primitive inventory is complete. The separately hashed independent native export attribution is linked from the release SELECTED_BUILD.json.';timing_report=$timingPath;timing_report_sha256=(Sha $timingPath);functional_rtl_changes=0;hardware_validated=$false}
    Save-Json ([System.IO.Path]::Combine($implementation,'resource-timing-summary.json')) $report;$script:Manifest.report=$report;$script:Manifest.stage='implemented';$script:Manifest.status=if($report.constraints_met){'timing_passed'}else{'timing_failed'};if($script:Manifest.Contains('error')){$script:Manifest.Remove('error')};Save-Manifest
    [System.IO.File]::AppendAllLines([System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'),[string[]]@(('MODIFIED PHYSICAL exact command: '+$invocation.executable+' '+($invocation.argv -join ' ')),('MODIFIED PHYSICAL input: '+$script:Build),('MODIFIED PHYSICAL literal result: '+$script:Manifest.status+' WNS='+$wns+'ns total_LUT='+$totals.lut+' total_FF='+$totals.ff),'MODIFIED PHYSICAL exit_status=0; timing failure is reported separately when present.'),$script:Bom)
    foreach($path in @($manifestPath,$timingPath,$nativePath,[System.IO.Path]::Combine($implementation,'resource-timing-summary.json'),[System.IO.Path]::Combine($implementation,'routed-primitive-inventory.json'),[System.IO.Path]::Combine($script:Build,'VERIFICATION.txt'))){[void][System.IO.File]::ReadAllBytes($path)}
    Write-Output ('BARE_BUILD_RESULT '+$script:Manifest.status+' WNS='+$wns+' LUT='+$totals.lut+' FF='+$totals.ff+' BUILD='+$script:Build)
    if(-not$report.constraints_met){exit 2};exit 0
}catch{if($null -ne $script:Manifest){$script:Manifest.status='failed';$script:Manifest.error=$_.Exception.Message;Save-Manifest};Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
finally{if($script:Held -and $null -ne $script:Mutex){$script:Mutex.ReleaseMutex()};if($null -ne $script:Mutex){$script:Mutex.Dispose()}}
