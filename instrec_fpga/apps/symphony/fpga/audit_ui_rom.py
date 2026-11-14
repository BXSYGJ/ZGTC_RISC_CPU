"""Audit the actual PDS UI-ROM INIT payload and output-bit connectivity.

This is an initialization-integrity audit. It does not replace the full-frame
RTL tests or prove the mapped pixel-to-font address-selection logic.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
sys.path.insert(0,str(PROJECT/"rtos"))
import audit_mapped_rom as primitive

ARRAYS={"font_rom":("font_q","symphony_font.hex",8192),
        "guide_rom":("guide_q","symphony_guide.hex",4096),
        "library_rom":("library_q","symphony_library.hex",4096)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(path,role):
    data=path.read_bytes()
    return {"role":role,"path":str(path.resolve()),"bytes":len(data),"sha256":digest(data)}


def image_words(path,depth):
    result=[0]*depth
    assigned=set();address=0
    for word in re.sub(r"//[^\n]*","",path.read_text(encoding="ascii")).split():
        if word.startswith("@"):
            address=int(word[1:],16);continue
        if not re.fullmatch(r"[0-9a-fA-F]{1,4}",word):raise ValueError("Invalid 16-bit HEX word")
        if address>=depth or address in assigned:raise ValueError("Out-of-range or duplicate HEX address")
        result[address]=int(word,16);assigned.add(address);address+=1
    if len(assigned)!=depth:raise ValueError("Generated UI image must explicitly cover its complete capacity")
    return result


def is_font(item):
    return bool(re.search(r"(?:^|/)font_rom(?:_|$)",item["source"]) or re.search(r"(?:^|/)font_rom(?:_|$)",item["name"]))


def is_tiles(item):
    return "guide_rom" in item["source"] or "guide_rom" in item["name"] or "library_rom" in item["source"] or "library_rom" in item["name"]


def context(module,index,font):
    values={"glyph":index>>5,"glyph_y":index&31} if font else {"tile_address":index}
    result={}
    for name,width in module.widths.items():
        base=name.rsplit("/",1)[-1]
        if base in values:
            for bit in range(width):result[name+"["+str(bit)+"]"]=(values[base]>>bit)&1
    for name,value in values.items():
        for bit in range(16):result[name+"["+str(bit)+"]"]=(value>>bit)&1
    return result


def output_bus(module,base):
    candidates=[name for name,width in module.widths.items() if name.rsplit("/",1)[-1]==base and width==16]
    if len(candidates)!=1:raise ValueError("Expected one actual 16-bit mapped output bus "+base+": "+repr(candidates))
    return candidates[0]


def reconstruct(module,array,expected):
    font=array=="font_rom"
    selected=[item for item in module.roms if (is_font(item) if font else is_tiles(item))]
    if not selected:raise ValueError("No physical DRM primitives for "+array)
    output=output_bus(module,ARRAYS[array][0])
    # PDS merges the two tile arrays and removes each unused constant-zero
    # palette MSB. Such a bit has no physical storage or mapped consumers.
    # Canonical zero is accepted only when the entire frozen image is zero
    # in that bit and the actual netlist contains no driver/reference.
    optimized=[]
    no_declarations=re.sub(r"\b(?:wire|input|output)\b[^;]*;","",module.text)
    for bit in range(16):
        name=output+"["+str(bit)+"]"
        references=re.search(re.escape(output)+r"\s*\[\s*"+str(bit)+r"\s*\]",no_declarations)
        range_reference=any(min(int(match[1]),int(match[2]))<=bit<=max(int(match[1]),int(match[2]))
                            for match in re.finditer(re.escape(output)+r"\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]",no_declarations))
        bare_reference=re.search(r"\b"+re.escape(output)+r"\b(?!\s*\[)",no_declarations)
        if name not in module.drivers and not references and not range_reference and not bare_reference:
            if any((word>>bit)&1 for word in expected):raise ValueError("Unstored mapped bit is not constant zero in frozen image")
            optimized.append(bit)
    cells={item["name"]:primitive.init_cells(item) for item in selected}
    actual=[];control_records={}
    for index in range(len(expected)):
        ctx=context(module,index,font)
        for bit in optimized:ctx[output+"["+str(bit)+"]"]=0
        for item in selected:
            ports,params=item["ports"],item["parameters"]
            is18="18K" in item["primitive"]
            for port in ("A","B"):
                nets=primitive.bits(ports.get("DO"+port,""),module.widths)
                if not nets:continue
                width=primitive.literal(params["DATA_WIDTH_"+port])[0]
                if width not in (1,2,4,8,9,16,18,32,36):raise ValueError("Unexpected physical DRM width")
                cache={}
                address=module.evaluate(ports["ADDR"+port],ctx,cache)
                cs=module.evaluate(ports.get("CS"+port,"3'b000"),ctx,cache)
                mask=primitive.literal(params.get("CS"+port+"_MASK","3'b000"))[0]
                controls={"we":module.evaluate(ports.get("WE"+port,"1'b0"),ctx,cache),
                          "ce":module.evaluate(ports.get("CE"+port,"1'b0"),ctx,cache),
                          "reset":module.evaluate(ports.get("RST"+port,"1'b0"),ctx,cache),
                          "hold":module.evaluate(ports.get("ADDR"+port+"_HOLD","1'b0"),ctx,cache)}
                if controls!={"we":0,"ce":1,"reset":0,"hold":0}:raise ValueError("Inactive ROM read controls")
                if primitive.canonical(ports.get("CLK"+port,""))!="pix_clk":raise ValueError("UI ROM read clock differs from pixel clock")
                if primitive.literal(params.get("DO"+port+"_REG","0"))[0]!=0:raise ValueError("Unexpected additional DRM output register")
                if cs!=mask:raise ValueError("Unexpected chip-select split; audit must evaluate its output selector")
                raw=primitive.raw_read(cells[item["name"]],address,width,is18)
                for pin,net in enumerate(nets):
                    if net.startswith("1'b"):continue
                    value=primitive.physical_output(raw,width,pin,is18,port)
                    if net in ctx and ctx[net]!=value:raise ValueError("Conflicting physical ROM output drivers")
                    ctx[net]=value
                control_records[item["name"]+":"+port]={"data_width":width,"clock":ports.get("CLK"+port),"controls":controls,"cs_mask":mask}
        actual.append(sum(module.evaluate(output+"["+str(bit)+"]",ctx,{})<<bit for bit in range(16)))
    differences=[{"word":i,"expected":f"{left:04x}","actual":f"{right:04x}"} for i,(left,right) in enumerate(zip(expected,actual)) if left!=right]
    payload=lambda words:b"".join(word.to_bytes(2,"little") for word in words)
    return {"array":array,"output_bus":output,"expected_words":len(expected),"reconstructed_words":len(actual),
            "all_words_match":not differences,"mismatch_count":len(differences),"mismatches":differences[:16],
            "nonzero_expected_words":sum(word!=0 for word in expected),"nonzero_reconstructed_words":sum(word!=0 for word in actual),
            "optimized_unused_zero_bits":optimized,"physical_compared_bits":len(expected)*(16-len(optimized)),
            "expected_words_sha256":digest(payload(expected)),"actual_words_sha256":digest(payload(actual)),
            "physical_read_controls":control_records,"instances":[item["name"] for item in selected]},selected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=HERE/"evidence"/"UI_ROM_AUDIT.json")
    parser.add_argument("--describe",action="store_true")
    args=parser.parse_args();run=args.run.resolve(strict=True)
    netlist=run/"synthesize"/"instrec_top_syn.vm"
    netlist_bytes=netlist.read_bytes()
    text=netlist_bytes.decode("utf-8",errors="strict")
    modules=primitive.module_list(text)
    selected=[module for module in modules if any(is_font(item) for item in module.roms)]
    if len(selected)!=1:raise ValueError("Expected one actual UI module with initialized font DRM")
    module=selected[0]
    if args.describe:
        print(json.dumps({"module":module.name,"nets":{name:width for name,width in module.widths.items() if any(term in name for term in ["glyph","tile_address","font_q","guide_q","library_q"])},
                          "roms":[{key:value for key,value in item.items() if key in ["name","source","primitive","ports"]}|{"parameters":{key:value for key,value in item["parameters"].items() if not key.startswith("INIT_")}} for item in module.roms if is_font(item) or is_tiles(item)]},indent=2))
        return 0
    report={"passed":False,"schema":"symphony-ui-rom-init-v1","started_utc":datetime.now(timezone.utc).isoformat(),"run":str(run),
            "scope":"all logical UI-ROM words reconstructed from actual synthesized DRM INIT and output-pin connectivity",
            "mapped_pixel_address_cone_verified":False,"address_boundary":"logical glyph/glyph_y or tile_address nets; upstream pixel-selection logic is outside this INIT audit",
            "arrays":[],"inputs":[],"errors":[]}
    try:
        mapdb=run/"device_map"/"instrec_top_map.adf"
        if not mapdb.is_file():raise ValueError("Actual device map is not yet available")
        flow=json.loads((run/"RESULT.json").read_text(encoding="utf-8-sig"))
        if flow.get("exit_code")!=0 or flow.get("errors") or flow.get("frozen_inputs_unchanged") is not True:
            raise ValueError("Actual mapped PDS flow did not finish cleanly")
        if not all(flow.get("stages",{}).get(stage) is True for stage in ("compile","synthesize","dev_map")):
            raise ValueError("Actual synthesis and device mapping must be complete")
        manifest=json.loads((run/"INPUTS.json").read_text(encoding="utf-8-sig"))
        inputs=[(netlist,"synthesized_netlist"),(mapdb,"mapped_database"),(run/"INPUTS.json","frozen_manifest"),
                (run/"RESULT.json","mapped_flow_result"),
                (run/"inputs"/"src"/"ui"/"symphony_renderer.v","frozen_renderer"),
                (Path(__file__),"auditor_source"),(PROJECT/"rtos"/"audit_mapped_rom.py","primitive_decode_helper"),
                (HERE/"gen_assets.py","asset_generator"),(HERE/"assets"/"ASSETS.json","asset_manifest")]
        if (run/"inputs"/"src"/"ui"/"symphony_renderer.v").read_bytes()!=(HERE/"symphony_renderer.v").read_bytes():raise ValueError("Current renderer differs from actual frozen input")
        required_sources=[HERE/"symphony_renderer.v",HERE/"gen_assets.py",HERE/"assets"/"ASSETS.json"]
        required_sources += [HERE/"assets"/spec[1] for spec in ARRAYS.values()]
        for path in required_sources:
            relative=path.relative_to(PROJECT).as_posix()
            rows=[row for row in manifest["application_source_files"] if row["path"]==relative]
            if len(rows)!=1 or rows[0]["sha256"]!=digest(path.read_bytes()):raise ValueError("Application source differs from frozen manifest: "+relative)
        for path in [run/"inputs"/"src"/"ui"/"symphony_renderer.v"]+[run/"inputs"/"src"/"ui"/spec[1] for spec in ARRAYS.values()]:
            relative=path.relative_to(run/"inputs").as_posix()
            rows=[row for row in manifest["files"] if row["path"]==relative]
            if len(rows)!=1 or rows[0]["sha256"]!=digest(path.read_bytes()):raise ValueError("Frozen UI file differs from manifest: "+relative)
        modelroot=Path(os.environ.get("PDS_ROOT","D:/PDS_2022.2-SP6.4"))/"arch"/"vendor"/"pango"/"verilog"/"simulation"
        inputs += [(modelroot/name,"vendor_drm_model") for name in ["GTP_DRM18K_E1.v","GTP_DRM36K_E1.v"]]
        for array,(_,filename,_) in ARRAYS.items():
            inputs += [(run/"inputs"/"src"/"ui"/filename,"frozen_"+array),
                       (run/"src"/"ui"/filename,"loaded_"+array),(HERE/"assets"/filename,"current_"+array)]
        before=[record(path,role) for path,role in inputs]
        if before[0]["sha256"]!=digest(netlist_bytes):raise ValueError("Synthesis netlist changed before reconstruction")
        physical={}
        for array,(_,filename,depth) in ARRAYS.items():
            frozen=run/"inputs"/"src"/"ui"/filename
            loaded=run/"src"/"ui"/filename
            if frozen.read_bytes()!=loaded.read_bytes():raise ValueError("Frozen and synthesizer HEX files differ")
            if frozen.read_bytes()!=(HERE/"assets"/filename).read_bytes():raise ValueError("Current checked-in UI asset differs from PDS input")
            result,instances=reconstruct(module,array,image_words(frozen,depth))
            report["arrays"].append(result)
            for item in instances:physical[item["name"]]=item
            if not result["all_words_match"]:raise ValueError("Actual initialized words differ in "+array)
        report["instances"]=[{"name":item["name"],"source":item["source"],"primitive":item["primitive"],"literal_sha256":digest(item["literal"].encode("utf-8")),
                              "init_cells_sha256":digest(b"".join(cell.to_bytes(2,"little") for cell in primitive.init_cells(item))),"ports":item["ports"]} for item in physical.values()]
        report["inputs"]=[record(path,role) for path,role in inputs]
        report["inputs_unchanged"]=report["inputs"]==before
        if not report["inputs_unchanged"]:raise ValueError("Audit inputs changed during reconstruction")
        report["covered_words"]=sum(row["reconstructed_words"] for row in report["arrays"])
        report["covered_payload_bits"]=report["covered_words"]*16
        report["physical_compared_bits"]=sum(row["physical_compared_bits"] for row in report["arrays"])
        report["passed"]=True
    except Exception as error:report["errors"].append(str(error))
    report["finished_utc"]=datetime.now(timezone.utc).isoformat()
    report["exit_status"]=0 if report["passed"] else 1
    report["command"]={"argv":[sys.executable,*sys.argv],"cwd":str(Path.cwd())}
    report["literal_output"]=("SYMPHONY_UI_ROM_AUDIT_PASS font=8192 guide=4096 library=4096 payload_bits=262144" if report["passed"] else "SYMPHONY_UI_ROM_AUDIT_FAIL "+"; ".join(report["errors"]))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if json.loads(args.out.read_text(encoding="utf-8"))["passed"]!=report["passed"]:raise ValueError("Report reopen failed")
    print(report["literal_output"],flush=True)
    return report["exit_status"]


if __name__=="__main__":raise SystemExit(main())
