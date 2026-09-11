import hashlib
import json
import re
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pds_report import parse_reports

SOURCE = EXPERIMENT / "build/pds/20260910-151146-f2a68b53"
BASELINE = ROOT / "build/regfile-valid-fanout-stage/build/pds/20260909-124605-a402f7e8"


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(filename):
    return json.loads(filename.read_text(encoding="utf-8-sig"))


def audit():
    snapshots = [load(directory / "source-snapshot.json") for directory in (BASELINE, SOURCE)]
    require(set(snapshots[0]["Files"]) == set(snapshots[1]["Files"]) and len(snapshots[0]["Files"]) == 20, "Unexpected source inventory")
    for directory, snapshot in zip((BASELINE, SOURCE), snapshots):
        require(Path(snapshot["Root"]).resolve() == (directory / "source").resolve(), "Wrong snapshot root")
        for relative, expected in snapshot["Files"].items():
            require(digest(directory / "source" / relative) == expected, "Captured source changed: " + relative)
    changes = [relative for relative in snapshots[0]["Files"] if snapshots[0]["Files"][relative] != snapshots[1]["Files"][relative]]
    require(changes == ["rtl/rv32_core.sv"], "More than the core changed")
    spec = load(EXPERIMENT / "source-delta.json")
    require(digest(BASELINE / "source/rtl/rv32_core.sv") == spec["baseline_core_sha256"].upper(), "Wrong baseline core")
    expected = (BASELINE / "source/rtl/rv32_core.sv").read_text(encoding="utf-8-sig")
    for before, after in spec["edits"]:
        require(expected.count(before) == 1, "Ambiguous source delta")
        expected = expected.replace(before, after)
    require(expected == (SOURCE / "source/rtl/rv32_core.sv").read_text(encoding="utf-8-sig"), "Unexpected core delta")
    require(digest(EXPERIMENT / "rtl/rv32_core.sv") == digest(SOURCE / "source/rtl/rv32_core.sv"), "Working core differs from PDS")
    firmware_hash = digest(SOURCE / "firmware.hex")
    require(firmware_hash == digest(BASELINE / "firmware.hex") == "0E5EAD297589F9689CE8D9D60163DD7DD87FD71FF7EC11731545DE9CD9E99ABF", "Wrong firmware")
    tops = [re.sub(r'\.INIT_FILE\("[^"]+"\)', '.INIT_FILE("FIRMWARE")', (directory / "pds_soc_top.v").read_text(encoding="utf-8-sig")) for directory in (BASELINE, SOURCE)]
    require(tops[0] == tops[1], "Generated top parameters differ")
    receipt = load(EXPERIMENT / "build/relation-regression.json")
    require(receipt["simulation_passed"], "Relation regression failed")
    for relative, expected_hash in receipt["sha256"].items():
        require(digest(EXPERIMENT / relative) == expected_hash.upper(), "Regression input changed")
    reports = [parse_reports((directory / "report_timing/pds_soc_top.rtr").read_text(encoding="utf-8-sig"), (directory / "run.log").read_text(encoding="utf-8-sig"), 157500000) for directory in (BASELINE, SOURCE)]
    evidence_files = ["source-snapshot.json", "pds_soc_top.v", "firmware.hex", "synthesize/pds_soc_top_syn.vm", "report_timing/pds_soc_top.rtr", "run.log", "generate_bitstream/pds_soc_top.sbit"]
    result = {"schema": 1, "evidence_consistent": True, "baseline_build": str(BASELINE), "candidate_build": str(SOURCE),
              "source_files": 20, "changed_sources": changes, "reports": {"ordinary_baseline": reports[0], "ordinary_candidate": reports[1]},
              "lut_change_same_ordinary_configuration": reports[1]["resources"]["post_route_luts"] - reports[0]["resources"]["post_route_luts"],
              "full_ila_evaluated": False, "hardware_validated": False, "coremark_score": None, "full_score_qualified": False,
              "decision": "Do not promote: ordinary timing gate failed; do not compare ordinary LUTs with the 9374-LUT full-ILA baseline",
              "output_sha256": {label: {relative: digest(directory / relative) for relative in evidence_files} for label, directory in (("baseline", BASELINE), ("candidate", SOURCE))},
              "regression_receipt_sha256": digest(EXPERIMENT / "build/relation-regression.json")}
    (EXPERIMENT / "build/ordinary-comparison-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    result = audit()
    print(json.dumps({name: result[name] for name in ("evidence_consistent", "changed_sources", "lut_change_same_ordinary_configuration", "decision")}, indent=2))
