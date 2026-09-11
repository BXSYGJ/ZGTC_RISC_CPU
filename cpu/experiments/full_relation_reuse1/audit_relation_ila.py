import argparse
import json
import re
from pathlib import Path

import stage_relation_physical as staging
import audit_full_ila as parent_audit
from audit_long_pair import portable
from audit_joint import validate_simulation_metadata
from run_long import verified_build

ROOT = Path(__file__).resolve().parent
PARENT = staging.PARENT
BASE = staging.BASE
PROJECT = staging.PROJECT
SOURCE = PROJECT / "build/pds/20260911-082214-6a099604"
digest = parent_audit.digest
require = parent_audit.require
validate_inventory = parent_audit.validate_inventory
validate_stage_inputs = parent_audit.validate_stage_inputs
normalize_pipeline_mapping = parent_audit.normalize_pipeline_mapping
validate_config = parent_audit.validate_config
qualify = parent_audit.qualify


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


validate_shorts = staging.validate_shorts


def binding(source=SOURCE):
    require(source.resolve().parent == (PROJECT / "build/pds").resolve(), "Wrong PDS project")
    parent = parent_audit.binding()
    record = read_json(ROOT / "build/physical-project-complete-inputs.json")
    require(Path(record["project"]).resolve() == PROJECT.resolve() and Path(record["parent"]).resolve() == PARENT.resolve(), "Wrong staged project or parent")
    require(record["parent_source_hashes"] == parent["physical_source_hashes"], "Parent physical sources differ")
    inventory = record["source_hashes"]
    require(len(inventory) == 20 and set(inventory) == set(parent["physical_source_hashes"]), "Incomplete physical source inventory")
    require({name for name in inventory if inventory[name] != parent["physical_source_hashes"][name]} == {"rtl/rv32_core.sv"},
            "Unexpected physical source delta")
    for relative, checksum in inventory.items():
        current = staging.candidate_source(relative)
        require(digest(current) == checksum == digest(PROJECT / relative), "Current or staged RTL changed")
    validate_inventory(read_json(source / "source-snapshot.json"), inventory, source)
    require(record["generator_sha256"] == digest(ROOT / "stage_relation_physical.py") == digest(PROJECT / "generator-original.py"), "Stage generator changed")
    require(record["functional"] == staging.validate_functional(), "Functional evidence changed since staging")
    configuration = read_json(BASE / "configuration.json")
    parameters = parent_audit.hardware_parameters(configuration)
    require(record["hardware_parameters"] == parameters == parent["hardware_parameters"] and record["clock_hz"] == configuration["ClockHz"] == 151200000,
            "Wrong hardware parameters or clock")
    for name, checksum in record["support_script_hashes"].items():
        require(digest(BASE / "scripts" / name) == checksum == digest(PROJECT / "scripts" / name), "PDS support script changed")
    firmware = read_json(BASE.parent / "full_mul_precompute_clock154285/build/coremark_v0_i6000_p2700000_f151200000_rv32gcc_rv32im_O3_unroll_relax.build.json")
    parent_audit.validate_firmware(firmware, False, 6000)
    require(digest(source / "firmware.hex") == record["parent_firmware_sha256"] == firmware["HexSha256"] == parent_audit.FIRMWARE_HASHES[False],
            "Wrong physical firmware")
    parent_audit.validate_wrapper((source / "pds_soc_top.v").read_text(encoding="utf-8-sig"), parameters, 151200000, source / "firmware.hex")
    require(('add_design "' + (source / "pds_soc_top.v").as_posix() + '"') in (source / "build.tcl").read_text(encoding="utf-8-sig"), "Synthesis wrapper not referenced")
    bound = {"schema": 1, "scope": "relation-reuse V0 physical source binding; not timing or score qualification", "source": str(source),
             "clock_hz": 151200000, "physical_source_hashes": inventory, "hardware_parameters": parameters,
             "firmware_sha256": digest(source / "firmware.hex")}
    validate_shorts(bound)
    return bound


def normalize_candidate_mapping(netlist, fic, output):
    canonical = "board/soc/unused_pipeline_valid[3]"
    local = "board/soc/core/pipeline_valid[3]"
    require("Project.unit<0>.dataChannel<35>=" + canonical in fic, "Missing native MEM-valid channel")
    modules = re.findall(r"\bmodule rv32_soc\b(.*?)\bendmodule\b", netlist, re.S)
    require(len(modules) == 1, "SoC module missing or ambiguous")
    instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", modules[0], re.S)
    require(len(instances) == 1, "CPU instance missing or ambiguous")
    connections = re.findall(r"\.pipeline_valid\s*\(\{([^}]+)\}\)", instances[0])
    require(len(connections) == 1, "Missing pipeline port connection")
    bits = [value.strip() for value in connections[0].split(",")]
    require(len(bits) == 5 and bits[1] == "unused_pipeline_valid[3]", "Wrong MEM-valid alias connection")
    normalize_pipeline_mapping(netlist, fic.replace(canonical, local), output)
    return fic, output, {local: canonical}


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
