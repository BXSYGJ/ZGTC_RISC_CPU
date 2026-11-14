"""Reopen the native application's actual simulation and complete PDS results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE))
import build_system as application_builder


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_record(record: dict, label: str) -> Path:
    path = Path(record["path"]).resolve(strict=True)
    require(path.is_file() and sha(path)==record["sha256"],label+" changed: "+str(path))
    if "bytes" in record:
        require(path.stat().st_size==record["bytes"],label+" length changed: "+str(path))
    return path


def verify_runtime_inputs(path: Path) -> dict:
    data = read(path)
    require(data.get("passed") is True and data.get("exit_status")==0,"Runtime weight framing did not pass")
    weights = (ROOT / "scripts/outputs/weights_image.bin").resolve()
    uploader = (ROOT / "scripts/weight_upload.py").resolve()
    records = data["files"]
    require(len(records)==2 and {verify_record(row,"Runtime input") for row in records}=={weights,uploader},
            "Runtime input set differs from the accepted eight-class files")
    expected_weight_sha = "19a74dbec29d3a0f16ab06dc30f70312849977de0c6b345710b046b1908f5d7a"
    require(weights.stat().st_size==691040 and sha(weights)==expected_weight_sha,"Runtime weights differ from the accepted eight-class image")
    require(data["command"][-3:]==["--image",str(weights),"--dry-run"]
            and str(uploader) in data["command"] and Path(data["cwd"]).resolve()==ROOT,
            "Runtime report does not describe the accepted dry-run command")
    require("691040 bytes, sha256 "+expected_weight_sha in data["output"]
            and "frames: 2701 (including end frame)" in data["output"],"Runtime dry-run literal output changed")
    return {"path":str(path.resolve()),"sha256":sha(path),"files":records,"exit_status":data["exit_status"]}


def verify_ui_rom_audit(path: Path, run: Path) -> dict:
    data = read(path)
    run = run.resolve(strict=True)
    require(data.get("schema")=="symphony-ui-rom-init-v1" and data.get("passed") is True
            and data.get("exit_status")==0 and data.get("inputs_unchanged") is True and not data["errors"],
            "UI-ROM initialization audit did not pass")
    require(Path(data["run"]).resolve()==run,"UI-ROM audit refers to another PDS run")
    literal = "SYMPHONY_UI_ROM_AUDIT_PASS font=8192 guide=4096 library=4096 payload_bits=262144"
    require(data["literal_output"]==literal,"UI-ROM audit literal result changed")
    argv = data["command"]["argv"]
    require("--run" in argv and Path(argv[argv.index("--run")+1]).resolve()==run
            and any(Path(arg).resolve()==HERE / "audit_ui_rom.py" for arg in argv if arg.endswith("audit_ui_rom.py"))
            and Path(data["command"]["cwd"]).resolve()==ROOT,"UI-ROM audit command binding changed")
    inputs = data["inputs"]
    require(len(inputs)==20 and all("bytes" in row for row in inputs),"UI-ROM audit input set is incomplete")
    actual = {(row["role"],verify_record(row,"UI-ROM audit input")) for row in inputs}
    expected = {
        ("synthesized_netlist",run / "synthesize/instrec_top_syn.vm"),
        ("mapped_database",run / "device_map/instrec_top_map.adf"),
        ("frozen_manifest",run / "INPUTS.json"),
        ("mapped_flow_result",run / "RESULT.json"),
        ("frozen_renderer",run / "inputs/src/ui/symphony_renderer.v"),
        ("auditor_source",HERE / "audit_ui_rom.py"),
        ("primitive_decode_helper",ROOT / "rtos/audit_mapped_rom.py"),
        ("asset_generator",HERE / "gen_assets.py"),
        ("asset_manifest",HERE / "assets/ASSETS.json"),
    }
    vendors = {item for item in actual if item[0]=="vendor_drm_model"}
    require(len(vendors)==2 and {item[1].name for item in vendors}=={"GTP_DRM18K_E1.v","GTP_DRM36K_E1.v"},
            "UI-ROM vendor primitive inputs changed")
    specifications = {"font_rom":("symphony_font.hex",8192,131072),
                      "guide_rom":("symphony_guide.hex",4096,61440),
                      "library_rom":("symphony_library.hex",4096,61440)}
    for array,(filename,_,_) in specifications.items():
        expected.update({("frozen_"+array,run / "inputs/src/ui" / filename),
                         ("loaded_"+array,run / "src/ui" / filename),
                         ("current_"+array,HERE / "assets" / filename)})
    require(actual==expected|vendors,"UI-ROM audit input roles or paths changed")
    arrays = data["arrays"]
    require(len(arrays)==3 and {row["array"] for row in arrays}==set(specifications),"UI-ROM audit arrays changed")
    from audit_ui_rom import image_words
    physical_instances = set()
    for row in arrays:
        filename,depth,physical_bits = specifications[row["array"]]
        words = image_words(run / "inputs/src/ui" / filename,depth)
        digest = hashlib.sha256(b"".join(word.to_bytes(2,"little") for word in words)).hexdigest()
        require(row["expected_words"]==depth and row["reconstructed_words"]==depth
                and row["all_words_match"] is True and row["mismatch_count"]==0 and row["mismatches"]==[],
                "UI-ROM audit does not cover every word: "+row["array"])
        require(row["expected_words_sha256"]==digest==row["actual_words_sha256"],
                "UI-ROM reconstructed word hash differs: "+row["array"])
        require(row["physical_compared_bits"]==physical_bits
                and row["nonzero_expected_words"]==sum(word!=0 for word in words)==row["nonzero_reconstructed_words"],
                "UI-ROM physical coverage or nonzero word count changed: "+row["array"])
        physical_instances.update(row["instances"])
    require(data["covered_words"]==16384 and data["covered_payload_bits"]==262144
            and data["physical_compared_bits"]==253952,"UI-ROM audit capacity changed")
    require(len(data["instances"])==8 and len(physical_instances)==8
            and {row["name"] for row in data["instances"]}==physical_instances,"UI-ROM physical instance coverage changed")
    return {"path":str(path.resolve()),"sha256":sha(path),"passed":True,"run":str(run),
            "covered_words":16384,"covered_payload_bits":262144,"physical_compared_bits":253952,"instances":8}


def verify_unit(path: Path, token: str, source_root: Path = ROOT) -> dict:
    data = read(path)
    require(data.get("passed") is True,"Simulation did not pass: "+str(path))
    require(bool(data.get("commands")),"Actual commands are missing: "+str(path))
    for command in data["commands"]:
        require(command.get("exit_code",command.get("exit_status")) == 0,
                "A simulation command failed: "+str(path))
    outputs = "\n".join(command.get("output",command.get("literal_stdout","") + command.get("literal_stderr",""))
                        for command in data["commands"])
    require(token in outputs,"Expected literal test result is missing: "+token)
    for flag in ("inputs_unchanged","sources_unchanged"):
        if flag in data:
            require(data[flag] is True,"Simulation input binding failed: "+flag+" "+str(path))
    for field in ("source_sha256","input_sha256"):
        for name,expected in data.get(field,{}).items():
            source = Path(name)
            if not source.is_absolute(): source = source_root / source
            require(sha(source)==expected,"Test "+field+" changed: "+str(source))
    for command in data["commands"]:
        if "log" in command and "sha256" in command:
            log = Path(command["log"])
            if not log.is_absolute(): log = path.parent / log
            require(sha(log)==command["sha256"],"Simulation command log changed: "+str(log))
            require(log.read_text(encoding="utf-8")==command["output"],"Simulation output differs from its log: "+str(log))
    if "output_decoder_sha256" in data:
        require(sha(ROOT / "rtos/sim/output_decode.py")==data["output_decoder_sha256"],"Pixel output decoder changed")
    return {"path":str(path),"sha256":sha(path),"literal_output":outputs}


def verify_full_bindings(run: Path, full: dict) -> None:
    require(full["status"]=="pass" and full["exit_code"]==0 and not full["errors"] and not full["timed_out"],
            "Full implementation did not complete")
    require(all(full["stages"].get(name) is True for name in ("pnr","report_timing","gen_bit_stream"))
            and full["fresh_bitstream"] and full["frozen_inputs_unchanged"]
            and full["source_controls_unchanged"] and full["mapped_database_reused_unchanged"],
            "The bitstream is not bound to the reviewed frozen inputs")
    controls = full["source_control_hashes"]
    require({"INPUTS.json","build.tcl","RESULT.json","ROM_AUDIT.json"}.issubset(controls),
            "Full implementation source controls are incomplete")
    for name,expected in controls.items():
        require(sha(run / name)==expected,"Full implementation source control changed: "+name)
    for relative,expected in (
        ("INPUTS.json",full["manifest_sha256"]),
        ("RESULT.json",full["source_map_result_sha256"]),
        ("device_map/instrec_top_map.adf",full["database_sha256_before"]),
        ("ROM_AUDIT.json",full["rom_audit"]["sha256"]),
    ):
        require(sha(run / relative)==expected,"Full implementation binding changed: "+relative)
    require(verify_record(full["rom_audit"],"Full ROM audit")== (run / "ROM_AUDIT.json").resolve(),
            "Full implementation refers to another run's ROM audit")
    require(verify_record(full["bitstream"],"Full bitstream")== (run / "generate_bitstream/instrec_top.sbit").resolve(),
            "Full implementation refers to another run's bitstream")
    require(verify_record(full["timing_report"],"Full timing report")== (run / "report_timing/instrec_top.rtr").resolve(),
            "Full implementation refers to another run's timing report")


def verify_resource_report(path: Path, run: Path, full: dict, input_count: int) -> dict:
    data = read(path)
    require(Path(data["run"]).resolve()==run.resolve(),"Resource report refers to another run")
    require(data["frozen_input_count"]==input_count and data["changed_inputs"]==[]
            and data["clock_contract"]["passed"] is True,"Resource report input/clock binding changed")
    for label,hash_field in (("timing_report","timing_sha256"),("bitstream","bitstream_sha256")):
        require(Path(data[label]).resolve()==Path(full[label]["path"]).resolve()
                and data[hash_field]==full[label]["sha256"],"Resource report "+label+" binding changed")
    require(data["timing"]["complete_ten_tables"] is True,"Final timing tables are incomplete")
    return {"path":str(path.resolve()),"sha256":sha(path),"qualified":data["qualified"],
            "resources":data["routed_resources"]}


def verify_collected_delivery(data: dict) -> Path:
    """Reopen every accepted binding before and after a release is copied."""
    require(data["status"]=="pass","Passing native delivery report required")
    run = Path(data["pds_run"]).resolve(strict=True)
    require(sha(run / "INPUTS.json")==data["manifest_sha256"],"Accepted input manifest changed")
    for label,relative in (("map","RESULT.json"),("implementation","FULL_RESULT.json"),("rom_audit","ROM_AUDIT.json")):
        require(verify_record(data[label],"Accepted "+label)==(run / relative).resolve(),
                "Accepted "+label+" refers to another run")
    manifest = read(run / "INPUTS.json")
    require(manifest.get("application")=="symphony-native-hdmi","Wrong application manifest")
    require(manifest["system_clock_hz"]==125000000 and manifest["pixel_clock_hz"]==148500000
            and manifest["placement_seed"]==2 and manifest["hold_fix_iterations"]==8,"Wrong accepted clock/implementation profile")
    for row in manifest["files"]:
        require(sha(run / "inputs" / row["path"])==row["sha256"],"Accepted frozen source changed: "+row["path"])
    for row in manifest["application_source_files"]:
        require(sha(ROOT / row["path"])==row["sha256"],"Accepted application source changed: "+row["path"])
    full = read(run / "FULL_RESULT.json")
    verify_full_bindings(run,full)
    for label in ("bitstream","timing_report"):
        require(verify_record(data[label],"Accepted "+label)==Path(full[label]["path"]).resolve()
                and data[label]["sha256"]==full[label]["sha256"],"Accepted "+label+" differs from the implementation")
    resource_path = verify_record(data["resource_report"],"Accepted resource/timing report")
    require(verify_resource_report(resource_path,run,full,len(manifest["files"]))==data["resource_report"],
            "Accepted resource/timing metadata changed")
    sys.path.insert(0,str(ROOT / "rtos"))
    from audit_mapped_rom import verify_report
    require(verify_report(run)["status"]=="pass","Accepted mapped ROM audit failed")
    ui_rom_path = verify_record(data["ui_rom_audit"],"Accepted UI-ROM audit")
    require(verify_ui_rom_audit(ui_rom_path,run)==data["ui_rom_audit"],"Accepted UI-ROM audit metadata changed")
    expected_units = {
        "state": ("SYMPHONY_STATE_PASS",ROOT),
        "commit_and_rollback": ("MODIFIED_PASS",ROOT),
        "pixel": ("SYMPHONY_RENDER_PASS",HERE),
        "integration": ("SYMPHONY_INTEGRATION_PASS",ROOT),
    }
    for label,(token,source_root) in expected_units.items():
        record = data["simulations"][label]
        report_path = verify_record(record,"Accepted "+label+" report")
        verify_unit(report_path,token,source_root)
    runtime_path = verify_record(data["runtime_inputs"],"Accepted runtime input report")
    require(verify_runtime_inputs(runtime_path)==data["runtime_inputs"],"Accepted runtime input metadata changed")
    pixel_path = Path(data["simulations"]["pixel"]["path"])
    pixels = read(pixel_path)
    require(pixels["fixture_only"] is True and pixels["inputs_unchanged"] is True,"Accepted pixel provenance changed")
    for image in pixels["screenshots"]:
        path = Path(image["file"])
        if not path.is_absolute(): path = pixel_path.parent / path
        require(sha(path)==image["sha256"] and image["size"]==[1920,1080],"Accepted RTL raster changed")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pds-run",type=Path,required=True)
    parser.add_argument("--pixel-report",type=Path,required=True)
    parser.add_argument("--integration-report",type=Path,required=True)
    parser.add_argument("--out",type=Path,default=HERE / "evidence/DELIVERY.json")
    args = parser.parse_args()
    run = args.pds_run.resolve(strict=True)
    manifest = read(run / "INPUTS.json")
    mapping = read(run / "RESULT.json")
    full = read(run / "FULL_RESULT.json")
    require(manifest.get("application")=="symphony-native-hdmi","Wrong application manifest")
    require(manifest["system_clock_hz"]==125000000 and manifest["pixel_clock_hz"]==148500000,
            "Wrong application clock profile")
    require(manifest["placement_seed"]==2 and manifest["hold_fix_iterations"]==8,"Implementation recipe changed")
    require(mapping["exit_code"]==0 and not mapping["errors"] and mapping["frozen_inputs_unchanged"],"System mapping failed")
    require(all(mapping["stages"][name] for name in ("compile","synthesize","dev_map")),"Mapping stages incomplete")
    require(full["status"]=="pass" and full["exit_code"]==0 and not full["errors"] and not full["timed_out"],
            "Full implementation did not complete")
    require(all(full["stages"].values()) and full["fresh_bitstream"] and full["frozen_inputs_unchanged"]
            and full["source_controls_unchanged"] and full["mapped_database_reused_unchanged"],
            "The bitstream is not bound to the reviewed frozen inputs")
    verify_full_bindings(run,full)
    for item in manifest["files"]:
        require(sha(run / "inputs" / item["path"])==item["sha256"],"Changed frozen input: "+item["path"])
    for item in manifest["application_source_files"]:
        require(sha(ROOT / item["path"])==item["sha256"],"Application changed after synthesis: "+item["path"])
    baseline = application_builder.load_rtos_builder().verify_sources()
    # Reuse the inherited audit's binding checks, including the actual map.adf.
    sys.path.insert(0,str(ROOT / "rtos"))
    from audit_mapped_rom import verify_report
    rom = verify_report(run)
    require(rom.get("status")=="pass","Mapped production ROM audit failed")
    bit = Path(full["bitstream"]["path"])
    timing = Path(full["timing_report"]["path"])
    require(bit.is_file() and bit.stat().st_size==full["bitstream"]["bytes"]
            and sha(bit)==full["bitstream"]["sha256"],"Bitstream changed or is incomplete")
    require(sha(timing)==full["timing_report"]["sha256"],"Final timing report changed")
    state = verify_unit(HERE / "evidence/STATE.json","SYMPHONY_STATE_PASS")
    commit_path = HERE / "evidence/commit/RESULT.json"
    commit = verify_unit(commit_path,"MODIFIED_PASS")
    transaction = read(commit_path)
    require(transaction["baseline_unchanged"] and transaction["modified_left_changed"]
            and transaction["restored_sha256"]==transaction["original_sha256"],"Independent rollback did not restore the original source")
    for key in ("MODIFIED_FILE.v","DIFF_FILE.patch","VERIFICATION.txt","ROLLBACK.sh"):
        artifact = Path(transaction["artifacts"][key])
        require(bool(artifact.read_bytes()),"Missing transaction artifact: "+key)
    require(sha(Path(transaction["artifacts"]["MODIFIED_FILE.v"]))==transaction["modified_sha256"],"Modified copy changed")
    require(sha(Path(transaction["original_path"]))==transaction["original_sha256"],"Original event source changed")
    pixel_path = args.pixel_report.resolve(strict=True)
    pixel = verify_unit(pixel_path,"SYMPHONY_RENDER_PASS",HERE)
    pixel_data = read(pixel_path)
    require(pixel_data["inputs_unchanged"] and pixel_data["fixture_only"],"Pixel test provenance or input binding missing")
    for image in pixel_data["screenshots"]:
        path = Path(image["file"])
        if not path.is_absolute(): path = pixel_path.parent / path
        require(sha(path)==image["sha256"] and image["size"]==[1920,1080],"RTL raster changed or wrong size")
    integration = verify_unit(args.integration_report.resolve(strict=True),"SYMPHONY_INTEGRATION_PASS")
    runtime = verify_runtime_inputs(HERE / "evidence/RUNTIME_INPUTS.json")
    ui_rom = verify_ui_rom_audit(HERE / "evidence/UI_ROM_AUDIT.json",run)
    resources = verify_resource_report(HERE / "evidence/PDS_TIMING_AND_RESOURCES.json",run,full,len(manifest["files"]))
    result={"status":"pass","collected_utc":datetime.now(timezone.utc).isoformat(),
            "branch":"rtos125-integration","application":"Native FPGA HDMI guide and recognition-window library",
            "display":{"connection":"FPGA HDMI","width":1920,"height":1080,"pixel_clock_hz":148500000,"latency_clocks":5},
            "key":{"pin":"C23","short":"select/filter","double":"bookmark","long":"switch page","debounce_ms":20,"double_ms":300,"long_ms":900},
            "model":{"classes":8,"semantics":"single-label class probabilities","source":"unchanged RTOS125 production NPU"},
            "history":{"depth":64,"time":"result arrival uptime milliseconds","volatile":True},
            "pds_run":str(run),"manifest_sha256":sha(run / "INPUTS.json"),
            "baseline":{"files":baseline["source_count"],"unchanged":True},
            "simulations":{"state":state,"commit_and_rollback":commit,"pixel":pixel,"integration":integration},
            "runtime_inputs":runtime,
            "ui_rom_audit":ui_rom,
            "resource_report":resources,
            "map":{"path":str(run / "RESULT.json"),"sha256":sha(run / "RESULT.json"),"seconds":mapping["seconds"]},
            "implementation":{"path":str(run / "FULL_RESULT.json"),"sha256":sha(run / "FULL_RESULT.json"),"seconds":full["seconds"]},
            "rom_audit":{"path":str(run / "ROM_AUDIT.json"),"sha256":sha(run / "ROM_AUDIT.json"),"status":"pass"},
            "bitstream":full["bitstream"],"timing_report":full["timing_report"],
            "timing_policy":"Retain the user's fixed working point and actual timing report",
            "physical_board_test":"pending"}
    verify_collected_delivery(result)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    require(read(args.out)==result,"Final evidence did not reopen exactly")
    print("SYMPHONY_DELIVERY_PASS inputs="+str(len(manifest["files"]))+" baseline="+str(baseline["source_count"])
          +" bit_sha256="+sha(bit)+" report="+str(args.out),flush=True)
    return 0


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
