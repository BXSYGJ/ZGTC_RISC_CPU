import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_id_relation_mask1"
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete"
CORE_MODULES = ["rv32_core","rv32_machine","rv32_decode","rv32_alu","rv32_btb","rv32_muldiv","rv32_cache","rv32_uncached","rv32_memory_system","rv32_burst_ram","rv32_burst_arbiter"]
sys.path.insert(0, str(PARENT))
import audit_full_ila as parent_audit
from audit_long_pair import portable
from audit_joint import validate_simulation_metadata
from run_long import verified_build

digest = parent_audit.digest
require = parent_audit.require


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def candidate_source(relative):
    return ROOT / Path(relative).name if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv") else BASE / relative


def validate_functional():
    receipt = read_json(ROOT / "change-receipt.json")
    require(receipt["parent"] == PARENT.name and digest(PARENT / "rv32_core.sv") == receipt["parent_core_sha256"], "Wrong relation parent")
    require(len(receipt["substitutions"]) == 1, "Wrong relation source delta")
    expected = (PARENT / "rv32_core.sv").read_text(encoding="utf-8")
    for before, after in receipt["substitutions"]:
        require(expected.count(before) == 1, "Ambiguous relation substitution")
        expected = expected.replace(before, after)
    require((ROOT / "rv32_core.sv").read_text(encoding="utf-8") == expected and digest(ROOT / "rv32_core.sv") == receipt["core_sha256"], "Relation candidate changed")
    require(digest(ROOT / "rv32_btb.sv") == digest(PARENT / "rv32_btb.sv") == receipt["btb_sha256"], "Predictor changed")
    for name, entry in receipt["files"].items():
        original = BASE / "rtl" / name
        require(digest(original) == entry["parent_sha256"], "Qualified ancestor changed")
        expected = original.read_text(encoding="utf-8")
        for before, after in entry["substitutions"]:
            require(expected.count(before) == 1, "Ambiguous ancestor substitution")
            expected = expected.replace(before, after)
        require((ROOT / name).read_text(encoding="utf-8") == expected and digest(ROOT / name) == entry["candidate_sha256"], "Candidate ancestry differs")
    observers = read_json(ROOT / "observer-receipt.json")
    require(set(observers) == {"core_tb.sv", "cached_core_tb.sv"}, "Incomplete relation observers")
    for name, entry in observers.items():
        original = ROOT.parent / entry["parent"]
        require(digest(original) == entry["parent_sha256"], "Original observer changed")
        expected = original.read_text(encoding="utf-8")
        for before, after in entry["substitutions"]:
            require(expected.count(before) == 1, "Ambiguous observer substitution")
            expected = expected.replace(before, after)
        require((ROOT / "sim" / name).read_text(encoding="utf-8") == expected and digest(ROOT / "sim" / name) == entry["observer_sha256"], "Relation observer changed")
    directory = ROOT / "build/core-regressions-coverage-groups"
    regression = read_json(directory / "manifest.json")
    require(regression["passed"] is True and len(regression["runs"]) == 16, "Incomplete core regression")
    require(digest(ROOT / "run_regressions.py") == regression["runner_sha256"] == digest(directory / "runner-original.py"), "Core regression runner changed")
    expected_inputs = {"rtl/" + name + ".sv" for name in CORE_MODULES} | {"sim/core_tb.sv", "sim/cached_core_tb.sv", "check_trace.py", "core_selftest.hex", "core_selftest.bin", "observer-receipt.json"}
    require(set(regression["source_hashes"]) == expected_inputs, "Incomplete core source inventory")
    for relative, checksum in regression["source_hashes"].items():
        if relative.startswith("rtl/"):
            current = candidate_source(relative)
        elif relative.startswith("sim/") or relative == "observer-receipt.json":
            current = ROOT / relative
        elif relative == "check_trace.py":
            current = BASE / "scripts" / relative
        else:
            require(relative in ("core_selftest.hex", "core_selftest.bin"), "Unknown core regression input")
            current = BASE / "build" / relative
        require(digest(current) == checksum == digest(directory / relative), "Core regression source changed: " + relative)
    require(len(regression["source_hashes"]) == 17, "Incomplete core source inventory")
    for relative, checksum in regression["outputs"].items():
        require(Path(relative).name == relative and digest(directory / relative) == checksum, "Core output changed")
    expected_names = {kind + "-p" + str(predictor) + "-l" + str(bubble) + "-" + seed
                      for kind in ("core", "cached") for predictor in (0, 1) for bubble in (0, 1)
                      for seed in (("12345678", "a5a5c3c3", "deadbeef") if kind == "core" else ("12345678",))}
    require({entry["name"] for entry in regression["runs"]} == expected_names, "Wrong regression configuration matrix")
    expected_outputs = {name + suffix for name in expected_names for suffix in (".trace", ".memory", ".log", "-reference.log")}
    expected_outputs |= {kind + "-p" + str(predictor) + "-l" + str(bubble) + suffix for kind in ("core", "cached") for predictor in (0, 1) for bubble in (0, 1) for suffix in (".vvp", "-compile.log")}
    expected_outputs |= {"check_trace.py", "core_selftest.hex", "core_selftest.bin", "observer-receipt.json", "runner-original.py"}
    require(set(regression["outputs"]) == expected_outputs, "Incomplete core output inventory")
    for entry in regression["runs"]:
        name = entry["name"]
        require(digest(directory / (name + ".trace")) == entry["trace_sha256"] and digest(directory / (name + ".memory")) == entry["memory_sha256"], "Core trace or memory differs")
        log = (directory / (name + ".log")).read_text(encoding="utf-8")
        marker = re.search(r"PASS relation reuse=([0-9]+) mem=([0-9]+) wb=([0-9]+) stalls=([0-9]+) load=([0-9]+) bubble=([01])", log)
        require(marker is not None, "Missing actual relation coverage")
        coverage = dict(zip(("reuse", "mem", "wb", "stalls", "load"), map(int, marker.groups()[:5])))
        require(coverage == entry["relation_coverage"] and int(marker[6]) == entry["parameters"]["LOAD_USE_BUBBLE"], "Relation coverage differs from log")
        require("PASS reference" in (directory / (name + "-reference.log")).read_text(encoding="utf-8"), "Independent reference did not pass")
    for kind in ("core", "cached"):
        for bubble in (0, 1):
            group = [entry for entry in regression["runs"] if entry["name"].startswith(kind + "-") and entry["parameters"]["LOAD_USE_BUBBLE"] == bubble]
            require(len(group) == (6 if kind == "core" else 2), "Wrong relation coverage group")
            for field in ("mem", "wb", "stalls", "load"):
                require(sum(entry["relation_coverage"][field] for entry in group) > 0, "Missing grouped forwarding coverage")
            require(all((entry["relation_coverage"]["reuse"] > 0) == bool(bubble) for entry in group), "Incorrect fallback activation")
    faults = ROOT / "build/relation-tests-186e1eff"
    fault_manifest = read_json(faults / "manifest.json")
    require(fault_manifest["passed"] is True and fault_manifest["inputs_unchanged"] is True and fault_manifest["tests_run"] == 3, "Relation fault suite incomplete")
    fault_inputs = [candidate_source("rtl/" + name + ".sv") for name in CORE_MODULES]
    fault_inputs += [PARENT / "rv32_core.sv", ROOT / "observer-receipt.json", ROOT / "change-receipt.json", ROOT / "test_relation_reuse.py", ROOT / "test_source_delta.py", ROOT / "sim/core_tb.sv", ROOT / "sim/cached_core_tb.sv", BASE / "build/core_selftest.hex"]
    require({portable(name) for name in fault_manifest["inputs"]} == {portable(path) for path in fault_inputs}, "Incomplete relation fault input inventory")
    fault_names = {name + ".sv" for name in CORE_MODULES} | {"cached_core_tb.sv", "test.vvp", "compile.log", "execute.log", "invocation.json", "trace.txt"}
    expected_fault_outputs = {"case-" + str(index) + "/" + name for index in range(1, 9) for name in fault_names}
    expected_fault_outputs |= {"case-" + str(index) + "/memory.txt" for index in range(5, 9)}
    require(set(fault_manifest["outputs"]) == expected_fault_outputs, "Incomplete relation fault output inventory")
    for path, checksum in fault_manifest["inputs"].items():
        portable_path = portable(path)
        require(portable_path.startswith(portable(ROOT.parents[1]) + "/") and "/../" not in portable_path, "Relation input outside CPU workspace")
        relative = portable_path[len(portable(ROOT.parents[1])) + 1:]
        require(digest(ROOT.parents[1] / relative) == checksum, "Relation fault source changed")
    for relative, checksum in fault_manifest["outputs"].items():
        require(not Path(relative).is_absolute() and ".." not in Path(relative).parts and digest(faults / relative) == checksum, "Relation fault output changed")
    for index in range(1, 9):
        case = faults / ("case-" + str(index))
        invocation = read_json(case / "invocation.json")
        require(invocation["compile_exit"] == 0, "Relation fault did not compile")
        log = (case / "execute.log").read_text(encoding="utf-8")
        if index <= 4:
            require(invocation["mutation"] is not None and invocation["execute_exit"] != 0 and "FAIL raw_relation_payload live operand relation mismatch" in log,
                    "Compiled relation fault was not rejected")
        else:
            require(invocation["mutation"] is None and invocation["execute_exit"] == 0 and "PASS cached_core" in log, "Live relation comparison failed")
    for reference_index, candidate_index in ((5, 6), (7, 8)):
        for name in ("trace.txt", "memory.txt", "execute.log"):
            require((faults / ("case-" + str(reference_index)) / name).read_bytes() == (faults / ("case-" + str(candidate_index)) / name).read_bytes(), "Live parent behavior differs")
    return {"regression_manifest_sha256": digest(directory / "manifest.json"), "core_runs": 16,
            "relation_manifest_sha256": digest(faults / "manifest.json"), "compiled_faults": 4,
            "source_delta_sha256": digest(ROOT / "change-receipt.json"), "observer_receipt_sha256": digest(ROOT / "observer-receipt.json")}


def validate_shorts(bound):
    for validation, reference_id in ((False, "20260910-233631-e15b5716"), (True, "20260910-233649-cc01ef34")):
        label = "v1" if validation else "v0"
        directory = ROOT / "build" / label
        reference = BASE / "build/compiled" / reference_id
        manifest = read_json(directory / "manifest.json")
        require(manifest["passed"] is True and manifest["validation_run"] is validation, "Incomplete short simulation")
        require(manifest["runner_sha256"] == digest(ROOT / "screen.py") == digest(directory / "runner-original.py"), "Short runner changed")
        previous, previous_result = verified_build(reference)
        validate_simulation_metadata(previous, bound, BASE)
        require(manifest["base_manifest_sha256"] == digest(reference / "manifest.json"), "Short reference changed")
        require(portable(manifest["base_build"]) == portable(reference), "Wrong short reference directory")
        require(manifest["firmware_build"] == previous["FirmwareBuild"], "Short firmware settings differ")
        require(manifest["firmware_sha256"] == previous["FirmwareSha256"] == digest(directory / "firmware.hex"), "Short firmware differs")
        require(manifest["hardware_parameters"] == bound["hardware_parameters"], "Short hardware parameters differ")
        require(set(manifest["source_hashes"]) == set(previous["SourceSnapshot"]), "Incomplete short source inventory")
        for relative, checksum in manifest["source_hashes"].items():
            require(digest(directory / "source" / relative) == checksum, "Captured short source changed")
            if relative.startswith("rtl/"):
                require(bound["physical_source_hashes"].get(relative) == checksum, "Physical and short RTL differ")
            else:
                require(digest(BASE / relative) == previous["SourceSnapshot"][relative] == checksum, "Short simulation driver changed")
        expected_command = [argument.replace(portable(reference), portable(directory)) for argument in previous["CompileCommand"]]
        require(manifest["compile_command"] == expected_command, "Short compiler command differs")
        require(set(manifest["outputs"]) == {"objects/Vrv32_soc", "uart.log", "result.json", "compile.log", "execute.log"}, "Incomplete short outputs")
        for name, checksum in manifest["outputs"].items():
            require(digest(directory / name) == checksum, "Short output changed")
        parent_run = PARENT / "build" / label
        require(manifest["parent_manifest_sha256"] == digest(parent_run / "manifest.json") and manifest["parent_short_uart_identical"] is True,
                "Parent short binding differs")
        require((directory / "uart.log").read_bytes() == (parent_run / "uart.log").read_bytes(), "Parent and candidate UART differ")
        result = parent_audit.check_simulation_result((directory / "uart.log").read_text(encoding="utf-8"), manifest["firmware_build"],
                                                     bound["hardware_parameters"], True)
        stored = read_json(directory / "result.json")
        require(stored["result"] == result and stored["cycles"] == result["cycles"], "Short result differs from raw UART")
        require(result["iterations"] == 10 and result["validation_run"] is validation, "Wrong short iterations or seed")
        require(stored["reference_cycles"] == previous_result["cycles"] and stored["cycles_saved"] == previous_result["cycles"] - result["cycles"],
                "Short comparison differs")


def prepare():
    functional = validate_functional()
    parent = parent_audit.binding()
    inventory = parent["physical_source_hashes"]
    candidate_inventory = {name: digest(candidate_source(name)) for name in inventory}
    require({name for name in inventory if candidate_inventory[name] != inventory[name]} == {"rtl/rv32_core.sv"}, "Unexpected complete-system delta")
    validate_shorts(dict(parent, physical_source_hashes=candidate_inventory))
    PROJECT.mkdir(parents=True, exist_ok=False)
    for relative, checksum in candidate_inventory.items():
        destination = PROJECT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate_source(relative), destination)
        require(digest(destination) == checksum, "Staged RTL copy differs")
    scripts = ("run_pds.ps1", "build_pds.tcl", "pds_soc_top.v.in", "pds_report.py")
    (PROJECT / "scripts").mkdir()
    for name in scripts:
        shutil.copyfile(BASE / "scripts" / name, PROJECT / "scripts" / name)
    shutil.copyfile(Path(__file__), PROJECT / "generator-original.py")
    record = {"schema": 1, "scope": "complete-source relation-reuse physical experiment; not ILA or score qualification",
              "parent": str(PARENT), "project": str(PROJECT), "source_hashes": candidate_inventory, "parent_source_hashes": inventory,
              "functional": functional, "support_script_hashes": {name: digest(PROJECT / "scripts" / name) for name in scripts},
              "generator_sha256": digest(Path(__file__)), "hardware_parameters": parent["hardware_parameters"], "clock_hz": parent["clock_hz"],
              "parent_firmware_sha256": parent["firmware_sha256"], "hardware_validated": False, "full_score_qualified": False, "baseline_replaced": False}
    (ROOT / "build/physical-project-complete-inputs.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    prepare()
