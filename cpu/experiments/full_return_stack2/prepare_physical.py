import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete-depthslice"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    inventory = json.loads((BASE / "source-inputs.json").read_text(encoding="utf-8-sig"))["source_hashes"]
    require(len(inventory) == 20 and "rtl/rv32_core.sv" in inventory, "Unexpected parent physical input inventory")
    for relative, expected in inventory.items():
        require(digest(BASE / relative) == expected, "Qualified parent source changed: " + relative)
    references = {"v0": "20260910-233631-e15b5716", "v1": "20260910-233649-cc01ef34"}
    for seed in ("v0", "v1"):
        screen = ROOT / "build" / (seed + "-depthslice")
        manifest = json.loads((screen / "manifest.json").read_text(encoding="utf-8"))
        result = json.loads((screen / "result.json").read_text(encoding="utf-8"))
        original = BASE / "build/compiled" / references[seed]
        require(manifest["passed"] is True and result["cycles_saved"] > 0, "Paired execution improvement not established")
        for filename in ("rv32_core.sv", "rv32_btb.sv"):
            require(digest(ROOT / filename) == manifest["source_hashes"]["rtl/" + filename], "Candidate differs from screened RTL")
        for filename, expected in manifest["outputs"].items():
            require(digest(screen / filename) == expected, "Screen output changed")
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
              "predictor_associativity": 1, "total_predictor_entries": 256, "return_stack_depth": 2,
              "hardware_parameters": json.loads((BASE / "configuration.json").read_text(encoding="utf-8-sig"))}
    require({relative for relative, expected in copies.items() if expected != inventory[relative]} == {"rtl/rv32_core.sv", "rtl/rv32_btb.sv"}, "Physical staging changes more than return-stack RTL")
    output = ROOT / "build/physical-project-complete-depthslice-inputs.json"
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
