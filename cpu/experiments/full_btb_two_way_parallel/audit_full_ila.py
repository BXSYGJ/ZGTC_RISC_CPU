import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete"
SOURCE = PROJECT / "build/pds/20260911-022751-c70713a8"
sys.path.insert(0, str(BASE))
from audit_binding import validate_wrapper
from audit_clock import validate_firmware
from audit_ila_mapping import digest, require, normalize_pipeline_mapping, validate_config, FIRMWARE_HASHES
from run_coremark_compiled import hardware_parameters
from qualify_full_ila import qualify


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_inventory(snapshot, expected, source):
    require(Path(snapshot["Root"]).resolve() == (source / "source").resolve(), "Wrong captured source root")
    require(snapshot["Files"] == expected, "Captured physical inventory differs")
    for relative, checksum in expected.items():
        require(digest(source / "source" / relative) == checksum, "Captured source changed: " + relative)


def validate_stage_inputs(stage, source):
    copies = {"source.adf": "synthesize/pds_soc_top_syn.adf", "netlist.v": "synthesize/pds_soc_top_syn.vm",
              "firmware.hex": "firmware.hex", "source-snapshot.json": "source-snapshot.json",
              "board.fdc": "source/constraints/board.fdc", "uart_remotelab.fdc": "source/constraints/uart_remotelab.fdc"}
    for target, original in copies.items():
        require(digest(stage / target) == digest(source / original), "Staged input differs: " + target)
    return copies


def binding(source=SOURCE):
    require(source.resolve().parent == (PROJECT / "build/pds").resolve(), "Wrong PDS project")
    record = read_json(ROOT / "build/physical-project-complete-inputs.json")
    require(Path(record["project"]).resolve() == PROJECT.resolve(), "Wrong staged project")
    require(Path(record["parent"]).resolve() == BASE.resolve(), "Wrong qualified parent")
    inventory = read_json(BASE / "source-inputs.json")["source_hashes"]
    require(digest(BASE / "source-inputs.json") == record["parent_source_inventory_sha256"], "Parent inventory changed")
    require(len(inventory) == 20 and set(record["source_hashes"]) == set(inventory), "Incomplete physical input set")
    require([name for name in inventory if inventory[name] != record["source_hashes"][name]] == ["rtl/rv32_btb.sv"], "Unexpected physical delta")
    for relative, expected in inventory.items():
        require(digest(BASE / relative) == expected, "Qualified parent source changed: " + relative)
        current = ROOT / "rv32_btb.sv" if relative == "rtl/rv32_btb.sv" else BASE / relative
        require(digest(current) == digest(PROJECT / relative) == record["source_hashes"][relative], "Staged source changed: " + relative)
    validate_inventory(read_json(source / "source-snapshot.json"), record["source_hashes"], source)
    configuration = read_json(BASE / "configuration.json")
    require(record["hardware_parameters"] == configuration and configuration["ClockHz"] == 151200000, "Wrong hardware configuration")
    parameters = hardware_parameters(configuration)
    for label, validation in (("v0", False), ("v1", True)):
        screen = ROOT / "build" / label
        manifest = read_json(screen / "manifest.json")
        require(manifest["passed"] is True and manifest["validation_run"] is validation, "Wrong or incomplete short run")
        require(manifest["hardware_parameters"] == parameters, "Short-run hardware differs")
        for relative, expected in manifest["source_hashes"].items():
            require(digest(screen / "source" / relative) == expected, "Captured screen source changed")
            if relative in inventory:
                require(expected == record["source_hashes"][relative], "Screen RTL differs from physical source")
        for name, expected in manifest["outputs"].items():
            require(digest(screen / name) == expected, "Screen output changed")
        require(digest(screen / "firmware.hex") == manifest["firmware_sha256"], "Short firmware changed")
        require(read_json(screen / "result.json")["cycles_saved"] > 0, "Execution improvement missing")
    require(digest(source / "firmware.hex") == FIRMWARE_HASHES[False], "Wrong V0 long firmware")
    firmware = read_json(BASE.parent / "full_mul_precompute_clock154285/build/coremark_v0_i6000_p2700000_f151200000_rv32gcc_rv32im_O3_unroll_relax.build.json")
    validate_firmware(firmware, False, 6000)
    require(firmware["HexSha256"] == digest(source / "firmware.hex"), "Long firmware manifest mismatch")
    validate_wrapper((source / "pds_soc_top.v").read_text(encoding="utf-8-sig"), parameters, 151200000, source / "firmware.hex")
    require(('add_design "' + (source / "pds_soc_top.v").as_posix() + '"') in (source / "build.tcl").read_text(encoding="utf-8-sig"), "Synthesis wrapper not referenced")
    for name, expected in record["support_script_hashes"].items():
        require(digest(PROJECT / "scripts" / name) == expected, "Staged support script changed")
    return {"schema": 1, "scope": "two-way BTB physical source binding, not timing or score qualification",
            "source": str(source), "clock_hz": 151200000, "physical_source_hashes": record["source_hashes"],
            "firmware_sha256": digest(source / "firmware.hex"), "hardware_parameters": parameters}


def normalize_candidate_mapping(netlist, fic, output):
    canonical = "board/soc/unused_pipeline_valid[3]"
    local = "board/soc/core/pipeline_valid[3]"
    require("Project.unit<0>.dataChannel<35>=" + canonical in fic, "Missing pipeline data channel")
    modules = re.findall(r"\bmodule rv32_soc\b(.*?)\bendmodule\b", netlist, re.S)
    require(len(modules) == 1, "Missing or ambiguous SoC module")
    instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", modules[0], re.S)
    require(len(instances) == 1, "Missing or ambiguous CPU instance")
    ports = re.findall(r"\.pipeline_valid\s*\(([^)]*)\)", instances[0])
    expected = r"{\core_pipeline_valid[4]_floating , unused_pipeline_valid[3], \core_pipeline_valid[2]_floating , \core_pipeline_valid[1]_floating , \core_pipeline_valid[0]_floating }"
    require(ports == [expected], "MEM-valid alias wiring differs")
    fic, output, aliases = normalize_pipeline_mapping(netlist, fic.replace(canonical, local), output.replace(canonical, local))
    return fic, output, {canonical: local}


def mapping(stage, source=SOURCE):
    require(stage.resolve().parent == (ROOT / "build/ila").resolve(), "Wrong ILA workspace")
    bound = binding(source)
    copies = validate_stage_inputs(stage, source)
    netlist = (stage / "netlist.v").read_text(encoding="utf-8-sig")
    fic = (stage / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
    output = (stage / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")
    require(not (stage / "verify-remapped.stderr.txt").read_text(encoding="utf-8-sig").strip(), "Inserter stderr is not empty")
    paths = re.findall(r"^Project.device.designInputFile=(.+)$", fic, re.M)
    require(len(paths) == 1 and Path(paths[0].strip()).resolve() == (stage / "source.adf").resolve(), "Wrong Inserter ADF")
    fic, output, aliases = normalize_candidate_mapping(netlist, fic, output)
    result = validate_config(fic, output)
    result.update({"schema": 1, "aliases": aliases, "alias_proof": "native pipeline register Q drivers and actual Inserter output",
                   "source_build": str(source), "binding": bound, "clock_hz": 151200000, "full_score_qualified": False,
                   "sha256": {name: digest(stage / name) for name in (*copies, "cpu-remapped.fic", "verify-remapped.stdout.txt", "verify-remapped.stderr.txt")}})
    destination = stage / "mapping-audit.json"
    text = json.dumps(result, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Mapping receipt changed")
    destination.write_text(text, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("binding", "mapping", "qualify"))
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--placement-seed", type=int, default=1)
    arguments = parser.parse_args()
    if arguments.mode == "binding":
        result = binding(arguments.source)
    else:
        require(arguments.stage is not None, "Stage is required")
        result = mapping(arguments.stage, arguments.source)
        if arguments.mode == "qualify":
            result = qualify(arguments.stage, audit_mapping=False, source=arguments.source, placement_seed=arguments.placement_seed)
            result["source_binding"] = binding(arguments.source)
            (arguments.stage / "physical-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if arguments.mode == "qualify":
        raise SystemExit(0 if result["physical_timing_passed"] else 2)
