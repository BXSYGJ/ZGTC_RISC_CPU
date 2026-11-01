param(
    [Parameter(Mandatory)][ValidateSet('Original_155250','H3_Base_145125','H3_Retained_145125')][string]$Release,
    [Parameter(Mandatory)][ValidateNotNullOrEmpty()][string]$BuildDirectory,
    [ValidateRange(2000000,10000000)][long]$Cycles = 2000000,
    [string]$SimulationRunDirectory
)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $utf8Bom=[System.Text.UTF8Encoding]::new($true)
    $utf8Plain=[System.Text.UTF8Encoding]::new($false)
    function Write-Json([string]$Path,$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 32),$utf8Bom)}
    function Get-Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    function To-Linux([string]$Path){$full=[System.IO.Path]::GetFullPath($Path);if($full -notmatch '^[A-Za-z]:'){throw 'Expected local drive path.'};'/mnt/'+$full.Substring(0,1).ToLowerInvariant()+'/'+$full.Substring(3).Replace([System.IO.Path]::DirectorySeparatorChar,'/')}
    function Replace-Once([string]$Text,[string]$Before,[string]$After){if([regex]::Matches($Text,[regex]::Escape($Before)).Count -ne 1){throw ('Capture edit anchor missing or ambiguous: '+$Before)};$Text.Replace($Before,$After)}
    function Run-Wsl([string[]]$Arguments,[string]$Prefix,[int]$TimeoutSeconds){
        $start=[System.Diagnostics.ProcessStartInfo]::new('wsl.exe');$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.StandardOutputEncoding=[System.Text.Encoding]::UTF8;$start.StandardErrorEncoding=[System.Text.Encoding]::UTF8
        foreach($argument in $Arguments){$start.ArgumentList.Add($argument)}
        $begin=[datetime]::UtcNow;$process=[System.Diagnostics.Process]::Start($start);$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit($TimeoutSeconds*1000)){$process.Kill($true);throw ('Local simulation timeout: '+$Prefix)}
        $out=$stdout.GetAwaiter().GetResult();$err=$stderr.GetAwaiter().GetResult();[System.IO.File]::WriteAllText(($Prefix+'.stdout.log'),$out,$utf8Bom);[System.IO.File]::WriteAllText(($Prefix+'.stderr.log'),$err,$utf8Bom)
        Write-Json ($Prefix+'.command.json') ([ordered]@{executable='wsl.exe';arguments=$Arguments;exit_code=$process.ExitCode;started_utc=$begin.ToString('o');finished_utc=[datetime]::UtcNow.ToString('o');stdout=$Prefix+'.stdout.log';stderr=$Prefix+'.stderr.log'})
        if($process.ExitCode -ne 0){throw ('Local simulation failed: '+$Prefix+' exit='+$process.ExitCode)}
        return $out
    }
    $task=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $workspace=[System.IO.Path]::GetDirectoryName($task)
    $releaseRoot=[System.IO.Path]::Combine($task,$Release)
    $build=[System.IO.Path]::GetFullPath($BuildDirectory)
    if(-not $build.StartsWith($releaseRoot+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Capture build must belong to the selected isolated release.'}
    $frozen=[System.IO.Path]::Combine($workspace,'Current_Paper_and_Sub7000_Core_Releases_20261012','cores',$Release)
    $recipe=Get-Content -LiteralPath ([System.IO.Path]::Combine($frozen,'recipe.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    $source=[System.IO.Path]::Combine($build,'inputs')
    $mappingPath=[System.IO.Path]::Combine($build,'implementation','mapping-audit.json')
    $mapping=Get-Content -LiteralPath $mappingPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    if($mapping.data.Count -ne 42){throw 'Expected the verified 42-bit native capture mapping.'}
    $names=@($mapping.data|Sort-Object channel|ForEach-Object{$_.native})
    $waveforms=[System.IO.Path]::Combine($releaseRoot,'waveforms')
    $run=if([string]::IsNullOrWhiteSpace($SimulationRunDirectory)){[System.IO.Path]::Combine($waveforms,'runs',([datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)))}else{[System.IO.Path]::GetFullPath($SimulationRunDirectory)}
    if(-not $run.StartsWith($waveforms+[System.IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Simulation run must belong to the selected release waveform directory.'}
    if([string]::IsNullOrWhiteSpace($SimulationRunDirectory)) {
    $inputs=[System.IO.Path]::Combine($run,'inputs');[void][System.IO.Directory]::CreateDirectory($inputs)
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($source,'rtl')) -Destination ([System.IO.Path]::Combine($inputs,'rtl')) -Recurse
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($frozen,'simulation','inputs','sim')) -Destination ([System.IO.Path]::Combine($inputs,'sim')) -Recurse
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($source,'firmware.hex')) -Destination ([System.IO.Path]::Combine($run,'firmware.hex'))
    $firmware=[System.IO.Path]::Combine($run,'firmware.hex')
    if((Get-Sha $firmware) -ne $recipe.roles.V0.firmware_sha256){throw 'Capture firmware differs from the unchanged frozen V0 firmware.'}
    $original=($Release -eq 'Original_155250')
    $observerName=if($original){'rv32_observed_soc.sv'}else{'native_selected_observer.sv'}
    $driverName=if($original){'driver.cpp'}else{'native_driver.cpp'}
    $observerPath=[System.IO.Path]::Combine($inputs,'sim',$observerName)
    $observer=[System.IO.File]::ReadAllText($observerPath).Replace("`r`n","`n")
    $observer=Replace-Once $observer 'output wire [2:0] redirect_kind' ('output wire [41:0] ila_capture_data,'+"`n"+'    output wire [2:0] redirect_kind')
    $assign=@('    assign ila_capture_data={soc.core.mem_fire,soc.core.frontend_fire,soc.core.mem_flush,soc.core.ex_fire,soc.core.id_fire,','        soc.core.wb_valid,soc.core.mem_valid,soc.core.ex_valid,soc.core.id_valid,soc.core.if_valid,soc.core.ex_pc};','    always @(posedge clk) if(rst_n) begin','        if(soc.core.id_fire && !soc.core.id_valid) $fatal(1,"ID transfer without valid");','        if(soc.core.ex_fire && !soc.core.ex_valid) $fatal(1,"EX transfer without valid");','        if(soc.core.mem_fire && !soc.core.mem_valid) $fatal(1,"MEM transfer without valid");','        if(soc.core.mem_flush && !soc.core.mem_fire) $fatal(1,"MEM flush without transfer");','    end') -join "`n"
    $observer=Replace-Once $observer 'endmodule' ($assign+"`nendmodule")
    [System.IO.File]::WriteAllText($observerPath,$observer,$utf8Plain)
    $driverPath=[System.IO.Path]::Combine($inputs,'sim',$driverName)
    $driver=[System.IO.File]::ReadAllText($driverPath).Replace("`r`n","`n")
    $driver=Replace-Once $driver '#include <cstdint>' ('#include <cstdint>'+"`n"+'#include <deque>'+"`n"+'#include <vector>')
    $declarations=@('struct CapturedEdge { uint64_t cycle, time_ps, data; };','        std::deque<CapturedEdge> history;','        std::vector<CapturedEdge> windows[3];','        bool triggered[3] = {};','        const uint32_t trigger_pc[3] = {0x942U,0x2604U,0x2e18U};','        const char *function_name[3] = {"core_bench_list","core_bench_matrix","core_bench_state"};','        uint64_t redirects[7] = {}') -join "`n"
    $driver=Replace-Once $driver 'uint64_t redirects[7] = {}' $declarations
    $timeExpression=if($original){'(sim_time + 5ULL) * 1000ULL'}else{'context.time()'}
    $capture=@('            const uint64_t capture_data = model->ila_capture_data;',('            const CapturedEdge capture_edge{cycle, '+$timeExpression+', capture_data};'),'            for (unsigned function=0; function<3; ++function) {','                if (!triggered[function] && history.size()==256 && ((capture_data >> 38) & 1ULL) && uint32_t(capture_data)==trigger_pc[function]) {','                    triggered[function]=true; windows[function].assign(history.begin(),history.end());','                }','                if (triggered[function] && windows[function].size()<1024) windows[function].push_back(capture_edge);','            }','            history.push_back(capture_edge); if (history.size()>256) history.pop_front();','            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;') -join "`n"
    $driver=Replace-Once $driver '            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;' $capture
    $finish=@('        if (model->trap_valid || model->maintenance_fault) throw std::runtime_error("Capture ended with a trap");','        for (unsigned function=0; function<3; ++function) {','            if (windows[function].size()!=1024) throw std::runtime_error("Missing complete function-entry window");','            std::ofstream raw(std::string(function_name[function])+".raw.csv",std::ios::binary);','            if (!raw) throw std::runtime_error("Cannot create raw waveform");','            raw << "Cycle,SimTimePs,Data\n";','            for (const auto &edge: windows[function]) raw << edge.cycle << "," << edge.time_ps << "," << edge.data << ''\n'';','            raw.flush(); if (!raw) throw std::runtime_error("Raw waveform write failed");','            std::cout << "CAPTURE_WINDOW_PASS function=" << function_name[function] << " samples=1024 trigger_sample=256 trigger_pc=0x" << std::hex << trigger_pc[function] << std::dec << ''\n'';','        }','        uart.flush(); model->final();','        std::cout << "LOCAL_RTL_CAPTURE_PASS cycles=" << max_cycles << " cycle_count=" << model->cycle_count << " retired=" << model->retired_count << ''\n'';','        return 0;') -join "`n"
    $driver=Replace-Once $driver '        throw std::runtime_error("RTL cycle limit exceeded");' $finish
    [System.IO.File]::WriteAllText($driverPath,$driver,$utf8Plain)
    $sourceInputs=[System.Collections.Generic.List[object]]::new()
    foreach($file in Get-ChildItem -LiteralPath $source -File -Recurse|Sort-Object FullName){$sourceInputs.Add([ordered]@{path=$file.FullName;sha256=(Get-Sha $file.FullName)})}
    $arguments=@($recipe.simulation.argv|ForEach-Object{$_.Replace('{RELEASE}/simulation/inputs',(To-Linux $inputs)).Replace('{OUTPUT}',(To-Linux $run))})
    $jobs=[array]::IndexOf($arguments,'-j');$arguments[$jobs+1]='1';$env:WSL_UTF8='1'
    Write-Json ([System.IO.Path]::Combine($run,'SOURCE_IDENTITY.json')) ([ordered]@{release=$Release;origin='LOCAL RTL SIMULATION';source_inputs=$sourceInputs.ToArray();firmware_sha256=(Get-Sha $firmware);observer_sha256=(Get-Sha $observerPath);driver_sha256=(Get-Sha $driverPath);functional_rtl_edits=0;simulation_only_observation_port_bits=42;cycle_limit=$Cycles})
    Write-Output ('LOCAL_CAPTURE_BUILD release='+$Release+' directory='+$run)
    $null=Run-Wsl (@('--cd','/tmp','--exec',$recipe.simulation.tool_original)+$arguments) ([System.IO.Path]::Combine($run,'compile')) 900
    $executable=[System.IO.Path]::Combine($run,'objects','Vrv32_observed_soc')
    $runOutput=Run-Wsl @('--cd',(To-Linux $run),'--exec',(To-Linux $executable),(To-Linux ([System.IO.Path]::Combine($run,'uart.log'))),$Cycles.ToString([Globalization.CultureInfo]::InvariantCulture)) ([System.IO.Path]::Combine($run,'simulate')) 180
    if($runOutput -notmatch 'LOCAL_RTL_CAPTURE_PASS' -or [regex]::Matches($runOutput,'CAPTURE_WINDOW_PASS').Count -ne 3){throw 'Incomplete recorded capture windows.'}
    } else {
        $original=($Release -eq 'Original_155250')
        $observerName=if($original){'rv32_observed_soc.sv'}else{'native_selected_observer.sv'}
        $driverName=if($original){'driver.cpp'}else{'native_driver.cpp'}
        $inputs=[System.IO.Path]::Combine($run,'inputs');$observerPath=[System.IO.Path]::Combine($inputs,'sim',$observerName);$driverPath=[System.IO.Path]::Combine($inputs,'sim',$driverName);$firmware=[System.IO.Path]::Combine($run,'firmware.hex')
        $identity=Get-Content -LiteralPath ([System.IO.Path]::Combine($run,'SOURCE_IDENTITY.json')) -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
        if($identity.release -ne $Release -or $identity.firmware_sha256 -ne (Get-Sha $firmware)){throw 'Existing simulation identity mismatch.'}
        if($identity.observer_sha256 -ne (Get-Sha $observerPath) -or $identity.driver_sha256 -ne (Get-Sha $driverPath)){throw 'Existing simulation driver or observer changed.'}
        $sourceInputs=[System.Collections.Generic.List[object]]::new();foreach($file in $identity.source_inputs){$sourceInputs.Add($file)}
        $runOutput=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($run,'simulate.stdout.log'))
        if($runOutput -notmatch 'LOCAL_RTL_CAPTURE_PASS'){throw 'Existing simulation has no successful capture receipt.'}
    }
    $windows=[System.Collections.Generic.List[object]]::new()
    $functions=@('core_bench_list','core_bench_matrix','core_bench_state')
    $addresses=@([uint32]0x942,[uint32]0x2604,[uint32]0x2e18)
    $scalarNames=@('if_valid','id_valid','ex_valid','mem_valid','wb_valid','id_fire','ex_fire','mem_flush','frontend_fire','mem_fire')
    for($function=0;$function -lt 3;$function++){
        $name=$functions[$function];$raw=[System.IO.Path]::Combine($run,($name+'.raw.csv'));$edges=@(Import-Csv -LiteralPath $raw -Encoding utf8)
        if($edges.Count -ne 1024){throw ('Unexpected sample count: '+$name)}
        $csv=[System.IO.Path]::Combine($waveforms,($name+'.csv'));$decoded=[System.IO.Path]::Combine($waveforms,($name+'.decoded.csv'));$vcd=[System.IO.Path]::Combine($waveforms,($name+'.vcd'))
        $csvLines=[System.Collections.Generic.List[string]]::new();$csvLines.Add((@('Sample')+$names+@('Cycle','Trigger','SimTimePs')) -join ',')
        $decodedLines=[System.Collections.Generic.List[string]]::new();$decodedLines.Add((@('Sample','Cycle','SimTimePs','EX_PC')+$scalarNames+@('Trigger')) -join ',')
        $vcdLines=[System.Collections.Generic.List[string]]::new();$vcdLines.AddRange([string[]]@('$date Generated from an observed local RTL simulation $end','$version Export-LocalIlaWaveforms.ps1 $end','$comment Simulator timestamps are retained. Configured FPGA frequency is separate metadata. $end','$timescale 1ps $end','$scope module local_rtl_pipeline $end','$var wire 1 K cpu_clk $end','$var wire 32 p ex_pc $end'))
        for($s=0;$s -lt 10;$s++){$vcdLines.Add('$var wire 1 '+[char](97+$s)+' '+$scalarNames[$s]+' $end')}
        $vcdLines.AddRange([string[]]@('$upscope $end','$enddefinitions $end','#0','0K'))
        $counts=[long[]]::new(10);$exStall=0;$memStall=0;$occupancy=0;$triggerCount=0;$distinct=[System.Collections.Generic.HashSet[uint32]]::new()
        for($sample=0;$sample -lt 1024;$sample++){
            $data=[uint64]::Parse($edges[$sample].Data,[Globalization.CultureInfo]::InvariantCulture);$cycle=[long]$edges[$sample].Cycle;$timePs=[long]$edges[$sample].SimTimePs
            if($sample -gt 0 -and ($cycle -ne ([long]$edges[$sample-1].Cycle+1) -or $timePs -ne ([long]$edges[$sample-1].SimTimePs+10000))){throw 'Waveform edges are not contiguous in the actual simulator timebase.'}
            $bits=for($bit=0;$bit -lt 42;$bit++){[int](($data -shr $bit) -band 1)}
            $pc=[uint32]($data -band [uint64]4294967295);$isTrigger=[int]($pc -eq $addresses[$function] -and $bits[38] -eq 1)
            if($sample -eq 256 -and $isTrigger -ne 1){throw 'Observed trigger edge does not match EX PC and EX transfer.'}
            $triggerCount+=$isTrigger;$csvLines.Add((@($sample)+$bits+@($cycle,$isTrigger,$timePs)) -join ',')
            $pcText='0x'+$pc.ToString('x8',[Globalization.CultureInfo]::InvariantCulture);$decodedLines.Add((@($sample,$cycle,$timePs,$pcText)+@($bits[32..41])+@($isTrigger)) -join ',')
            $vcdLines.Add('#'+$timePs);$vcdLines.Add('b'+[Convert]::ToString([long]$pc,2).PadLeft(32,'0')+' p')
            for($s=0;$s -lt 10;$s++){$vcdLines.Add([string]$bits[32+$s]+[char](97+$s));$counts[$s]+=$bits[32+$s];if($s -lt 5){$occupancy+=$bits[32+$s]}}
            $vcdLines.Add('1K');$vcdLines.Add('#'+($timePs+5000));$vcdLines.Add('0K')
            if($bits[34] -eq 1 -and $bits[38] -eq 0){$exStall++};if($bits[35] -eq 1 -and $bits[41] -eq 0){$memStall++};if($bits[38] -eq 1){[void]$distinct.Add($pc)}
        }
        [System.IO.File]::WriteAllLines($csv,[string[]]$csvLines,$utf8Bom);[System.IO.File]::WriteAllLines($decoded,[string[]]$decodedLines,$utf8Bom);[System.IO.File]::WriteAllLines($vcd,[string[]]$vcdLines,$utf8Plain)
        $signalCounts=[ordered]@{};for($s=0;$s -lt 10;$s++){$signalCounts[$scalarNames[$s]]=$counts[$s]}
        $windows.Add([ordered]@{function=$name;csv=$csv;vcd=$vcd;decoded_csv=$decoded;csv_sha256=(Get-Sha $csv);vcd_sha256=(Get-Sha $vcd);decoded_csv_sha256=(Get-Sha $decoded);raw_csv=$raw;raw_csv_sha256=(Get-Sha $raw);trigger_pc=('0x'+$addresses[$function].ToString('x8'));trigger_sample=256;observed_trigger_matches=$triggerCount;samples=1024;first_cycle=[long]$edges[0].Cycle;last_cycle=[long]$edges[-1].Cycle;first_sim_time_ps=[long]$edges[0].SimTimePs;last_sim_time_ps=[long]$edges[-1].SimTimePs;statistics=[ordered]@{scope='This recorded 1024-edge function-entry window';signal_asserted_samples=$signalCounts;ex_transfer_fraction=$counts[6]/1024.0;id_transfer_fraction=$counts[5]/1024.0;mem_transfer_fraction=$counts[9]/1024.0;mean_valid_stage_fraction=$occupancy/(1024.0*5);ex_valid_without_transfer_samples=$exStall;mem_valid_without_transfer_samples=$memStall;distinct_ex_transfer_pcs=$distinct.Count}})
    }
    $elf=[System.IO.Path]::Combine($frozen,'firmware','V0','firmware.elf')
    $manifest=[ordered]@{schema='local-rtl-pipeline-windows/v1';release=$Release;origin='LOCAL RTL SIMULATION';clock_hz=[long]$recipe.clock_hz;configured_fpga_clock_hz=[long]$recipe.clock_hz;simulation_clock_hz=3200;uart_baud=100;simulation_driver_clock_period_ps=10000;simulation_driver_timestamp_basis=if($original){'Original driver sc_time_stamp counter; 5 timestamp units per half-cycle, converted from ns to ps'}else{'Native VerilatedContext time in ps; native_tick raises the clock before advancing 5000 ps'};axis='sampled CPU edge index';hardware_validated=$false;complete_coremark_run=$false;firmware_iterations=6000;firmware_sha256=(Get-Sha $firmware);elf=[ordered]@{path=$elf;sha256=(Get-Sha $elf)};mapping_audit=[ordered]@{path=$mappingPath;sha256=(Get-Sha $mappingPath)};source_inputs=$sourceInputs.ToArray();simulation_observer=$observerPath;simulation_driver=$driverPath;simulation_run_directory=$run;simulation_exit_code=0;cycle_limit=$Cycles;trigger_predicate='EX_PC equals the exact ELF function entry and ex_fire equals 1; Trigger is a derived annotation, not an extra hardware probe';capture_shape='256 preceding observed edges, trigger at Sample 256, 767 following edges';windows=$windows.ToArray();generated_utc=[datetime]::UtcNow.ToString('o')}
    $manifestPath=[System.IO.Path]::Combine($waveforms,'WAVEFORM_MANIFEST.json');Write-Json $manifestPath $manifest
    foreach($window in $windows){foreach($path in @($window.csv,$window.vcd,$window.decoded_csv,$window.raw_csv)){[void][System.IO.File]::ReadAllBytes($path)}};[void][System.IO.File]::ReadAllText($manifestPath)
    Write-Output $runOutput.Trim();Write-Output ('WAVEFORM_MANIFEST='+$manifestPath)
    exit 0
} catch {Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
