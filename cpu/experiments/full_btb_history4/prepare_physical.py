import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PROJECT = ROOT / "build/physical-project-complete"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    predictor = (ROOT / "rv32_btb.sv").read_text(encoding="utf-8")
    require(predictor.count("parameter integer HISTORY_BITS=4,") == 1, "Wrong history width default")
    require(predictor.count("parameter integer COUNTER_BITS=2") == 1, "Wrong counter width default")
    inventory = json.loads((BASE / "source-inputs.json").read_text(encoding="utf-8-sig"))["source_hashes"]
    require(len(inventory) == 20 and "rtl/rv32_btb.sv" in inventory, "Unexpected parent physical input inventory")
    for relative, expected in inventory.items():
        require(digest(BASE / relative) == expected, "Qualified parent source changed: " + relative)
    for seed in ("v0", "v1"):
        screen = ROOT / "build" / seed
        manifest = json.loads((screen / "manifest.json").read_text(encoding="utf-8"))
        result = json.loads((screen / "result.json").read_text(encoding="utf-8"))
        require(manifest["passed"] is True and result["cycles_saved"] > 0, "Paired execution improvement not established")
        require(digest(ROOT / "rv32_btb.sv") == manifest["source_hashes"]["rtl/rv32_btb.sv"], "Predictor differs from screened RTL")
        for filename, expected in manifest["outputs"].items():
            require(digest(screen / filename) == expected, "Screen output changed")
    PROJECT.mkdir(parents=True, exist_ok=False)
    copies = {}
    for relative in inventory:
        source = ROOT / "rv32_btb.sv" if relative == "rtl/rv32_btb.sv" else BASE / relative
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
              "predictor_associativity": 1, "total_predictor_entries": 256,
              "hardware_parameters": dict(json.loads((BASE / "configuration.json").read_text(encoding="utf-8-sig")),
                                          Purpose="Four-bit local history with two-bit counters; not qualified", HistoryBits=4, CounterBits=2)}
    require([relative for relative, expected in copies.items() if expected != inventory[relative]] == ["rtl/rv32_btb.sv"], "Physical staging changes more than predictor RTL")
    output = ROOT / "build/physical-project-complete-inputs.json"
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
