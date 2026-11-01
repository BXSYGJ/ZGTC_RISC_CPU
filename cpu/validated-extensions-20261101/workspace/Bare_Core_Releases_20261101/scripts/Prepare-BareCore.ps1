param([Parameter(Mandatory)][ValidateSet('Original_155250','H3_Base_145125','H3_Retained_145125')][string]$Release)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
try {
    $bom=[System.Text.UTF8Encoding]::new($true)
    $plain=[System.Text.UTF8Encoding]::new($false)
    function Save-Json([string]$Path,$Value){[System.IO.File]::WriteAllText($Path,($Value|ConvertTo-Json -Depth 32),$bom)}
    function Sha([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
    $task=[System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot,'..'))
    $workspace=[System.IO.Path]::GetDirectoryName($task)
    $ila=[System.IO.Path]::Combine($workspace,'ILA_Core_Releases_20261101')
    $sourceWaveform=[System.IO.Path]::Combine($ila,$Release,'waveforms','WAVEFORM_MANIFEST.json')
    $waveform=Get-Content -LiteralPath $sourceWaveform -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
    $sourceRows=@($waveform.source_inputs|Where-Object {[System.IO.Path]::GetFileName($_.path) -eq 'rv32_core.sv'})
    if($sourceRows.Count -ne 1){throw 'Source waveform must identify one exact frozen core.'}
    $frozenRtl=[System.IO.Path]::GetDirectoryName($sourceRows[0].path)
    $releaseRoot=[System.IO.Path]::Combine($task,$Release)
    $source=[System.IO.Path]::Combine($releaseRoot,'source')
    $rtl=[System.IO.Path]::Combine($source,'rtl')
    $existingPath=[System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json')
    if(Test-Path -LiteralPath $existingPath){
        $existing=Get-Content -LiteralPath $existingPath -Raw -Encoding utf8|ConvertFrom-Json -AsHashtable
        if($existing.release -ne $Release -or $existing.functional_rtl_changes -ne 0 -or $existing.rtl.Count -ne 8 -or (Sha $sourceWaveform) -ne $existing.source_waveform_manifest_sha256){throw 'Existing frozen extraction provenance differs.'}
        foreach($row in $existing.rtl){if((Sha $row.path) -ne $row.sha256 -or (Sha $row.source) -ne $row.sha256){throw ('Existing extraction source identity differs: '+$row.name)}}
        foreach($key in @('wrapper','physical_fixture','boundary')){if((Sha $existing[$key].path) -ne $existing[$key].sha256){throw ('Existing extraction boundary differs: '+$key)}}
        foreach($path in @($existingPath,$existing.wrapper.path,$existing.physical_fixture.path,$existing.boundary.path)){[void][System.IO.File]::ReadAllBytes($path)}
        Write-Output ('BARE_PREPARE_EXISTING_PASS release='+$Release+' unchanged_rtl_files=8 source_manifest_preserved=true')
        Write-Output ('SOURCE_MANIFEST='+$existingPath)
        exit 0
    }
    [void][System.IO.Directory]::CreateDirectory($rtl)
    $closure=@('rv32_core.sv','rv32_rvc_frontend.sv','rv32_rvc_expand.sv','rv32_decode.sv','rv32_alu.sv','rv32_muldiv.sv','rv32_btb.sv','rv32_machine.sv')
    $hashes=[System.Collections.Generic.List[object]]::new()
    foreach($name in $closure){
        $original=[System.IO.Path]::Combine($frozenRtl,$name);$destination=[System.IO.Path]::Combine($rtl,$name)
        $row=@($waveform.source_inputs|Where-Object {$_.path -eq $original})
        if($row.Count -ne 1 -or (Sha $original) -ne $row[0].sha256){throw ('Frozen waveform source hash mismatch: '+$name)}
        if(Test-Path -LiteralPath $destination){if((Sha $destination) -ne (Sha $original)){throw ('Existing bare copy differs from frozen source: '+$name)}}else{Copy-Item -LiteralPath $original -Destination $destination}
        $hashes.Add([ordered]@{name=$name;path=$destination;source=$original;sha256=(Sha $destination)})
    }
    if(@(Get-ChildItem -LiteralPath $rtl -File).Count -ne 8){throw 'Bare core RTL directory must contain exactly its eight transitive source files.'}
    $core=[System.IO.File]::ReadAllText([System.IO.Path]::Combine($rtl,'rv32_core.sv'))
    $portHeader=[regex]::Match($core,'(?s)\)\s*\((.*?)\);').Groups[1].Value
    $declarations=[regex]::Matches($portHeader,'(?m)^\s*(input|output)\s+wire\s*(\[(\d+):(\d+)\])?\s*([^\r\n]+)')
    $ports=[System.Collections.Generic.List[object]]::new()
    foreach($declaration in $declarations){
        $width=if($declaration.Groups[2].Success){[int]$declaration.Groups[3].Value-[int]$declaration.Groups[4].Value+1}else{1}
        foreach($name in $declaration.Groups[5].Value.Trim().TrimEnd(',').Split(',')){$ports.Add([ordered]@{direction=$declaration.Groups[1].Value;name=$name.Trim();width=$width;range=$declaration.Groups[2].Value})}
    }
    $bits=($ports.width|Measure-Object -Sum).Sum
    if($bits -ne $(if($Release -eq 'Original_155250'){616}else{648})){throw 'Parsed core port bit count differs from the frozen boundary contract.'}
    $parameters=[ordered]@{RESET_VECTOR=0;ENABLE_PREDICTOR=1;ENABLE_M=1;ENABLE_C=1;FETCH_ADDRESS_BITS=16;FETCH_OVERLAP=1;EARLY_D_REQUEST=1;BTB_INDEX_BITS=8;BTB_ADDRESS_BITS=16;LOAD_USE_BUBBLE=1}
    if($Release -eq 'H3_Retained_145125'){$parameters.RETAIN_MUL_ELIGIBILITY=1}
    Save-Json ([System.IO.Path]::Combine($source,'parameters.json')) $parameters
    Save-Json ([System.IO.Path]::Combine($releaseRoot,'params.json')) $parameters
    $wrapper=[System.Collections.Generic.List[string]]::new();$wrapper.Add('`timescale 1ns/1ps');$wrapper.Add('(* syn_hier="fixed" *) module rv32_bare_core (')
    for($i=0;$i -lt $ports.Count;$i++){$p=$ports[$i];$wrapper.Add('    '+$p.direction+' wire '+$(if($p.range){$p.range+' '}else{''})+$p.name+$(if($i -lt $ports.Count-1){','}else{''}))}
    $wrapper.Add(');');$wrapper.Add('    (* syn_hier="fixed", syn_noprune=1 *) rv32_core #(')
    $parameterNames=@($parameters.Keys)
    for($i=0;$i -lt $parameterNames.Count;$i++){$name=$parameterNames[$i];$wrapper.Add('        .'+$name+'('+$parameters[$name]+')'+$(if($i -lt $parameterNames.Count-1){','}else{''}))}
    $wrapper.Add('    ) dut (')
    for($i=0;$i -lt $ports.Count;$i++){$name=$ports[$i].name;$wrapper.Add('        .'+$name+'('+$name+')'+$(if($i -lt $ports.Count-1){','}else{''}))}
    $wrapper.Add('    );');$wrapper.Add('endmodule')
    $wrapperPath=[System.IO.Path]::Combine($source,'rv32_bare_core.sv');[System.IO.File]::WriteAllLines($wrapperPath,[string[]]$wrapper,$plain)
    $inputPorts=@($ports|Where-Object {$_.direction -eq 'input' -and $_.name -ne 'clk'})
    $outputPorts=@($ports|Where-Object {$_.direction -eq 'output'})
    $inputBits=[int](($inputPorts.width|Measure-Object -Sum).Sum);$outputBits=[int](($outputPorts.width|Measure-Object -Sum).Sum)
    $fixture=[System.Collections.Generic.List[string]]::new();$fixture.AddRange([string[]]@('`timescale 1ns/1ps','module bare_core_scan_top (','    input wire clk, fixture_reset_n, scan_in, scan_shift, scan_update, scan_capture,','    output wire scan_out',');',('    localparam integer INPUT_BITS='+$inputBits+';'),('    localparam integer OUTPUT_BITS='+$outputBits+';'),'    (* syn_preserve=1 *) reg [INPUT_BITS-1:0] input_shift, active_inputs;','    (* syn_preserve=1 *) reg [OUTPUT_BITS-1:0] output_shift;','    wire [OUTPUT_BITS-1:0] core_outputs;','    assign scan_out=output_shift[0];','    always @(posedge clk or negedge fixture_reset_n) begin','        if(!fixture_reset_n) begin input_shift<=0; active_inputs<=0; output_shift<=0; end','        else begin','            if(scan_shift) input_shift<={input_shift[INPUT_BITS-2:0],scan_in};','            if(scan_update) active_inputs<=input_shift;','            if(scan_capture) output_shift<=core_outputs;','            else if(scan_shift) output_shift<={1''b0,output_shift[OUTPUT_BITS-1:1]};','        end','    end'))
    $inputMapping=[System.Collections.Generic.List[object]]::new();$outputMapping=[System.Collections.Generic.List[object]]::new();$inputOffset=0;$outputOffset=0
    foreach($p in $ports){if($p.name -eq 'clk'){$p['connection']='clk';continue};if($p.direction -eq 'input'){$offset=$inputOffset;$inputOffset+=$p.width;$bank='active_inputs';$list=$inputMapping}else{$offset=$outputOffset;$outputOffset+=$p.width;$bank='core_outputs';$list=$outputMapping};$p['connection']=$bank+$(if($p.width -eq 1){'['+$offset+']'}else{'['+($offset+$p.width-1)+':'+$offset+']'});$list.Add([ordered]@{port=$p.name;width=$p.width;lsb=$offset;msb=($offset+$p.width-1);connection=$p.connection})}
    $fixture.Add('    (* syn_hier="fixed", syn_noprune=1 *) rv32_bare_core core_boundary (')
    for($i=0;$i -lt $ports.Count;$i++){$p=$ports[$i];$fixture.Add('        .'+$p.name+'('+$p.connection+')'+$(if($i -lt $ports.Count-1){','}else{''}))}
    $fixture.Add('    );');$fixture.Add('endmodule')
    $fixturePath=[System.IO.Path]::Combine($source,'bare_core_scan_top.sv');[System.IO.File]::WriteAllLines($fixturePath,[string[]]$fixture,$plain)
    $boundary=[ordered]@{module='rv32_bare_core';dut='rv32_core';dut_hierarchy='core_boundary/dut';physical_top='bare_core_scan_top';all_port_bits=$bits;core_input_bits_including_clk=($inputBits+1);scan_controlled_input_bits=$inputBits;individually_captured_output_bits=$outputBits;input_mapping=$inputMapping.ToArray();output_mapping=$outputMapping.ToArray();ports=$ports.ToArray();parameters=$parameters;hierarchy_policy='syn_hier=fixed on rv32_bare_core and rv32_core';input_update='All core input bits except clk are scan-controlled active registers, atomically updated from input_shift. No core input is tied to a constant.';output_observation='Every output bit is captured separately and shifted out. There is no XOR/signature compression.';physical_clock='Direct external clk; no PLL, clock gating, or ILA.'}
    Save-Json ([System.IO.Path]::Combine($source,'BOUNDARY.json')) $boundary
    $manifest=[ordered]@{schema='bare-core-source/v1';release=$Release;configured_clock_hz=[long]$waveform.clock_hz;clock_uncertainty_ns=0.150;source_waveform_manifest=$sourceWaveform;source_waveform_manifest_sha256=(Sha $sourceWaveform);rtl=$hashes.ToArray();parameters=$parameters;wrapper=[ordered]@{path=$wrapperPath;sha256=(Sha $wrapperPath)};physical_fixture=[ordered]@{path=$fixturePath;sha256=(Sha $fixturePath)};boundary=[ordered]@{path=[System.IO.Path]::Combine($source,'BOUNDARY.json');sha256=(Sha ([System.IO.Path]::Combine($source,'BOUNDARY.json')))};functional_rtl_changes=0;included_modules=$closure;excluded_from_dut=@('cache','memory_system','burst_ram','peripherals','uart','pll','ila');status='prepared_no_physical_build_started';generated_utc=[datetime]::UtcNow.ToString('o')}
    Save-Json ([System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json')) $manifest
    $analysis=[System.IO.Path]::Combine($task,'analysis');[void][System.IO.Directory]::CreateDirectory($analysis)
    Copy-Item -LiteralPath ([System.IO.Path]::Combine($ila,'analysis','BARE_CORE_PREPARATION.md')) -Destination ([System.IO.Path]::Combine($analysis,'BARE_CORE_PREPARATION.md')) -Force
    foreach($file in @($wrapperPath,$fixturePath,[System.IO.Path]::Combine($source,'parameters.json'),[System.IO.Path]::Combine($source,'BOUNDARY.json'),[System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json'))){[void][System.IO.File]::ReadAllText($file)}
    Write-Output ('BARE_PREPARE_PASS release='+$Release+' unchanged_rtl_files=8 port_bits='+$bits+' input_scan_bits='+$inputBits+' output_capture_bits='+$outputBits)
    Write-Output ('SOURCE_MANIFEST='+[System.IO.Path]::Combine($releaseRoot,'SOURCE_MANIFEST.json'))
    exit 0
} catch {Write-Error -Message $_.Exception.Message -ErrorAction Continue;exit 1}
