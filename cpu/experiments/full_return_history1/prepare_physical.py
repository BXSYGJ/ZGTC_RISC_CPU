import hashlib
import json
import shutil
from pathlib import Path
from candidate_sources import PARENT, OVERRIDES, source_path
from run_safety import audit as audit_safety

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_regressions():
    directory = ROOT / "build/core-regressions"
    record = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    expected_names = {"cached-p0-12345678", "cached-p1-12345678"}
    expected_names.update("core-p" + str(predictor) + "-" + seed for predictor in (0, 1) for seed in ("12345678", "a5a5c3c3", "deadbeef"))
    require(record["passed"] is True and len(record["runs"]) == 8 and {run["name"] for run in record["runs"]} == expected_names, "Incomplete current core/cache regression")
    require(record["runner_sha256"] == digest(ROOT / "run_regressions.py"), "Regression runner changed")
    for relative, checksum in record["source_hashes"].items():
        if relative.startswith("rtl/"):
            current = source_path(relative)
        elif relative.startswith("sim/"):
            current = PARENT / relative
        elif relative == "check_trace.py":
            current = BASE / "scripts/check_trace.py"
        else:
            require(relative in ("core_selftest.hex", "core_selftest.bin"), "Unknown regression input")
            current = BASE / "build" / relative
        require(digest(current) == checksum == digest(directory / relative), "Regression input changed: " + relative)
    require(set(OVERRIDES).issubset(record["source_hashes"]), "Regression omits modified RTL")
    for name, checksum in record["outputs"].items():
        require(digest(directory / name) == checksum, "Regression output changed")
    for run in record["runs"]:
        name = run["name"]
        require(run["trace_sha256"] == digest(directory / (name + ".trace")) and run["memory_sha256"] == digest(directory / (name + ".memory")), "Regression trace/memory binding differs")
        require("PASS " in (directory / (name + ".log")).read_text() and "PASS " in (directory / (name + "-reference.log")).read_text(), "Raw regression/reference pass missing")
    return {"manifest_sha256": digest(directory / "manifest.json"), "runs": 8}


def main():
    inventory = json.loads((BASE / "source-inputs.json").read_text(encoding="utf-8-sig"))["source_hashes"]
    require(len(inventory) == 20 and "rtl/rv32_core.sv" in inventory, "Unexpected parent physical input inventory")
    for relative, expected in inventory.items():
        require(digest(BASE / relative) == expected, "Qualified parent source changed: " + relative)
    references = {"v0": "20260910-233631-e15b5716", "v1": "20260910-233649-cc01ef34"}
    for seed in ("v0", "v1"):
        screen = ROOT / "build" / seed
        manifest = json.loads((screen / "manifest.json").read_text(encoding="utf-8"))
        result = json.loads((screen / "result.json").read_text(encoding="utf-8"))
        original = PARENT / "build" / seed
        previous = json.loads((original / "result.json").read_text(encoding="utf-8"))["result"]
        for field in ("validation_run", "iterations", "retired", "seed_crc", "final_crc", "clock_hz"):
            require(result["result"][field] == previous[field], "One-entry architectural or firmware result changed: " + field)
        require(manifest["passed"] is True and result["cycles_saved"] > 0, "Paired execution improvement not established")
        for filename in ("rv32_core.sv", "rv32_btb.sv"):
            require(digest(ROOT / filename) == manifest["source_hashes"]["rtl/" + filename], "Candidate differs from screened RTL")
        for filename, expected in manifest["outputs"].items():
            require(digest(screen / filename) == expected, "Screen output changed")
    from test_source_delta import validate
    validate((ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text())
    core_evidence = validate_regressions()
    safety_evidence = audit_safety()
    PROJECT.mkdir(parents=True, exist_ok=False)
    copies = {}
    for relative in inventory:
        source = ROOT / Path(relative).name if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv") else BASE / relative
        destination = PROJECT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copies[relative] = digest(destination)
    scripts = ("run_pds.ps1", "build_pds.tcl", "pds_soc_top.v.in", "pds_report.py")
    (PROJECT / "scripts").mkdir(parents=True, exist_ok=True)
    for name in scripts:
        shutil.copyfile(BASE / "scripts" / name, PROJECT / "scripts" / name)
    shutil.copyfile(Path(__file__), PROJECT / "generator-original.py")
    record = {"schema": 1, "scope": "immutable generated PDS staging project; not implementation qualification",
              "parent": str(BASE), "project": str(PROJECT), "source_hashes": copies,
              "parent_source_inventory_sha256": digest(BASE / "source-inputs.json"),
              "support_script_hashes": {name: digest(PROJECT / "scripts" / name) for name in scripts},
              "requires_explicit_firmware": True, "generator_sha256": digest(Path(__file__)),
              "core_evidence": core_evidence, "safety_evidence": safety_evidence, "core_delta_receipt_sha256": digest(ROOT / "change-receipt.json"),
              "source_selector_sha256": digest(ROOT / "candidate_sources.py"),
              "predictor_associativity": 1, "total_predictor_entries": 256, "return_stack_depth": 1,
              "hardware_parameters": json.loads((BASE / "configuration.json").read_text(encoding="utf-8-sig"))}
    require({relative for relative, expected in copies.items() if expected != inventory[relative]} == {"rtl/rv32_core.sv", "rtl/rv32_btb.sv"}, "Physical staging changes more than return-stack RTL")
    output = ROOT / "build/physical-project-complete-inputs.json"
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
