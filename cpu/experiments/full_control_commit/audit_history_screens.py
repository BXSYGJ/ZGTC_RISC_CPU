import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from audit_short import digest, read_run, require

RUNS = {
    "full_history_fold0": [
        "20260910-214719-1f4d104b",
        "20260910-214731-ce9abfb1"
    ],
    "full_history_fold1": [
        "20260910-214745-739147e5",
        "20260910-214757-e33e0da1"
    ],
    "full_history_fold2": [
        "20260910-214448-b1927372",
        "20260910-214501-4f67ab27"
    ],
    "full_history_shared_confidence": [
        "20260910-215449-7b55fac5",
        "20260910-215502-57e22475"
    ]
}
PARENT_RUNS = ("20260910-195856-6bf511dd", "20260910-195908-6ac62ce5")


def compare(name, identifiers):
    candidate_root = ROOT.parent / name
    inputs = json.loads((candidate_root / "source-inputs.json").read_text(encoding="utf-8"))
    require(set(inputs["source_hashes"]) == set(inputs["parent_hashes"]), "Physical source set differs")
    changed = []
    for relative, expected in inputs["source_hashes"].items():
        require(digest(candidate_root / relative) == expected, "Current candidate source changed: " + relative)
        require(digest(ROOT / relative) == inputs["parent_hashes"][relative], "Parent source changed: " + relative)
        if expected != inputs["parent_hashes"][relative]:
            changed.append(relative)
    require(changed == ["rtl/rv32_btb.sv"], "Unexpected physical change set")
    pairs = []
    for validation, identifier in enumerate(identifiers):
        before_path = ROOT / "build/compiled" / PARENT_RUNS[validation]
        after_path = candidate_root / "build/compiled" / identifier
        before, reference = read_run(before_path)
        after, candidate = read_run(after_path)
        require(before["FirmwareBuild"] == after["FirmwareBuild"] and before["FirmwareSha256"] == after["FirmwareSha256"], "Firmware changed")
        require(before["HardwareParameters"] == after["HardwareParameters"], "Non-predictor hardware parameters differ")
        for field in ("SimulationBackend", "SimulationClockHz", "UartModelClockHz"):
            require(before[field] == after[field], "Simulation configuration changed: " + field)
        before_command = [argument.replace(before["BuildDirectory"], "BUILD") for argument in before["CompileCommand"]]
        after_command = [argument.replace(after["BuildDirectory"], "BUILD") for argument in after["CompileCommand"]]
        require(before_command == after_command, "Compile commands differ beyond paths")
        require(before["SourceSnapshot"].keys() == after["SourceSnapshot"].keys(), "Simulation source set differs")
        delta = [relative for relative in before["SourceSnapshot"] if before["SourceSnapshot"][relative] != after["SourceSnapshot"][relative]]
        require(delta == ["rtl/rv32_btb.sv"], "Unexpected simulation source change")
        for relative, expected in after["SourceSnapshot"].items():
            require(digest(candidate_root / relative) == expected, "Current simulation source changed: " + relative)
        for field in ("retired", "seed_crc", "final_crc", "validation_run", "iterations", "clock_hz"):
            require(reference[field] == candidate[field], "Architectural or test configuration differs: " + field)
        require(candidate["validation_run"] is bool(validation), "Wrong validation seed")
        require(after["ConfigurationInput"]["HistoryBits"] == 4, "Wrong history metadata")
        pairs.append({"validation": bool(validation), "parent_run": PARENT_RUNS[validation], "candidate_run": identifier,
                      "parent_cycles": reference["cycles"], "candidate_cycles": candidate["cycles"],
                      "extra_cycles": candidate["cycles"] - reference["cycles"],
                      "throughput_change_percent": (reference["cycles"] / candidate["cycles"] - 1) * 100,
                      "retired": candidate["retired"], "final_crc": candidate["final_crc"],
                      "parent_manifest_sha256": digest(before_path / "manifest.json"),
                      "candidate_manifest_sha256": digest(after_path / "manifest.json")})
    return {"experiment": name, "pairs": pairs, "source_inputs_sha256": digest(candidate_root / "source-inputs.json"),
            "both_short_runs_faster": all(pair["extra_cycles"] < 0 for pair in pairs),
            "physical_qualification_performed": False, "hardware_validated": False, "full_score_qualified": False}


def main():
    results = [compare(name, identifiers) for name, identifiers in RUNS.items()]
    report = {"scope": "matched ten-iteration execution screening only, not complete metric qualification",
              "results": results, "audit_sha256": digest(Path(__file__)), "parent_replaced": False}
    (ROOT / "build/history-screen-comparison.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()

