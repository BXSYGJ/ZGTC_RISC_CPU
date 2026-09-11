import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_id_relation_mask1"
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete"
sys.path.insert(0, str(PARENT))
from audit_full_ila import binding, digest, require
from candidate_sources import source_path
from audit_long_pair import portable


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_functional():
    directory = ROOT / "build/functional-1205ce4f"
    manifest = read_json(directory / "manifest.json")
    require(manifest["passed"] is True and manifest["sources_unchanged"] is True and manifest["tests_run"] == 3,
            "Peripheral functional suite did not pass completely")
    sources = [ROOT / name for name in ("rv32_peripherals.sv", "change-receipt.json", "banked_observer.sv.in", "test_banked_reads.py")]
    sources += [ROOT.parents[1] / "sim/peripherals_tb.sv"]
    sources += [BASE / "rtl" / name for name in ("rv32_peripherals.sv", "rv32_fifo.sv", "rv32_uart.sv")]
    actual = {portable(path): digest(path) for path in sources}
    require({portable(name): checksum for name, checksum in manifest["sources"].items()} == actual, "Peripheral functional sources changed")
    names = ("candidate.sv", "reference.sv", "testbench.sv", "compile.log", "execute.log", "invocation.json", "test.vvp")
    expected = {"case-" + str(index) + "/" + name for index in range(1, 7) for name in names}
    require(set(manifest["outputs"]) == expected, "Incomplete peripheral functional outputs")
    for name, checksum in manifest["outputs"].items():
        require(digest(directory / name) == checksum, "Peripheral functional output changed: " + name)
    for index in range(1, 7):
        stage = directory / ("case-" + str(index))
        invocation = read_json(stage / "invocation.json")
        require(invocation["compile_exit"] == 0, "Peripheral compilation failed")
        log = (stage / "execute.log").read_text(encoding="utf-8")
        if index == 6:
            require(invocation["mutation"] is None and invocation["execute_exit"] == 0, "Peripheral positive control failed")
            require("exhaustive_low_addresses=2048 high_bit_alias_reads=10752 snapshots=16" in log and "PASS peripherals" in log,
                    "Incomplete peripheral behavioral coverage")
            require(digest(stage / "candidate.sv") == digest(ROOT / "rv32_peripherals.sv"), "Tested peripheral differs from candidate")
        else:
            require(invocation["mutation"] is not None and invocation["execute_exit"] != 0 and "FAIL banked differential" in log,
                    "Missing compiled negative control")
    receipt = read_json(ROOT / "change-receipt.json")
    original = (BASE / "rtl/rv32_peripherals.sv").read_text(encoding="utf-8")
    require(digest(BASE / "rtl/rv32_peripherals.sv") == receipt["parent_sha256"], "Original peripheral changed")
    require(len(receipt["substitutions"]) == 2, "Wrong peripheral delta")
    for before, after in receipt["substitutions"]:
        require(original.count(before) == 1, "Ambiguous peripheral substitution")
        original = original.replace(before, after)
    require((ROOT / "rv32_peripherals.sv").read_text(encoding="utf-8") == original, "Peripheral structural delta changed")
    require(digest(ROOT / "rv32_peripherals.sv") == receipt["candidate_sha256"], "Peripheral candidate hash differs")
    return {"directory": str(directory), "manifest_sha256": digest(directory / "manifest.json"), "source_hashes": actual}


def prepare():
    functional = validate_functional()
    physical = binding()
    inventory = physical["physical_source_hashes"]
    require(len(inventory) == 20, "Incomplete parent physical inventory")
    require(inventory["rtl/rv32_peripherals.sv"] == digest(BASE / "rtl/rv32_peripherals.sv"), "Test reference differs from physical parent")
    PROJECT.mkdir(parents=True, exist_ok=False)
    copies = {}
    for relative, checksum in inventory.items():
        original = source_path(relative)
        require(digest(original) == checksum, "Parent physical source changed: " + relative)
        candidate = ROOT / "rv32_peripherals.sv" if relative == "rtl/rv32_peripherals.sv" else original
        destination = PROJECT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate, destination)
        copies[relative] = digest(destination)
    require({name for name in copies if copies[name] != inventory[name]} == {"rtl/rv32_peripherals.sv"}, "Unexpected complete-system source delta")
    scripts = ("run_pds.ps1", "build_pds.tcl", "pds_soc_top.v.in", "pds_report.py")
    (PROJECT / "scripts").mkdir()
    for name in scripts:
        shutil.copyfile(BASE / "scripts" / name, PROJECT / "scripts" / name)
    shutil.copyfile(Path(__file__), PROJECT / "generator-original.py")
    record = {"schema": 1, "scope": "complete-source ordinary physical experiment; not full-ILA or score qualification",
              "parent": str(PARENT), "project": str(PROJECT), "source_hashes": copies,
              "parent_source_hashes": inventory, "functional": functional,
              "support_script_hashes": {name: digest(PROJECT / "scripts" / name) for name in scripts},
              "generator_sha256": digest(Path(__file__)), "hardware_parameters": physical["hardware_parameters"],
              "clock_hz": physical["clock_hz"], "parent_firmware_sha256": physical["firmware_sha256"],
              "hardware_validated": False, "full_score_qualified": False, "baseline_replaced": False}
    (ROOT / "build/physical-project-complete-inputs.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    prepare()
