import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from run_coremark_compiled import verify_artifacts


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def read_run(path):
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8-sig"))
    if not manifest["SimulationPassed"]:
        raise ValueError("Simulation not passed")
    verify_artifacts(path, manifest)
    for name, key in (("coremark.sim.uart", "UartSha256"), ("result.json", "ResultSha256")):
        if digest(path / name) != manifest[key]:
            raise ValueError("Output changed: " + name)
    result = json.loads((path / "result.json").read_text())
    if not result["crc_valid"] or result["iterations"] != 10:
        raise ValueError("Wrong short-run result")
    return manifest, result


def main():
    baseline = ROOT.parent / "full_mul_precompute/build/compiled"
    builds = (("20260910-182155-21b1a5a3", "20260910-185649-657d23f4"),
              ("20260910-182451-55ded0e4", "20260910-185738-824cc956"))
    receipt = {"schema": 1, "scope": "same-firmware short RTL comparisons, not official CoreMark or hardware", "pairs": []}
    for validation, (before_id, after_id) in enumerate(builds):
        before_path = baseline / before_id
        after_path = ROOT / "build/compiled" / after_id
        before, reference = read_run(before_path)
        after, candidate = read_run(after_path)
        if before["HardwareParameters"] != after["HardwareParameters"] or before["FirmwareSha256"] != after["FirmwareSha256"]:
            raise ValueError("Firmware or parameter mismatch")
        if before["SimulationBackend"] != after["SimulationBackend"]:
            raise ValueError("Compiler backend mismatch")
        before_command = [argument.replace(before["BuildDirectory"], "BUILD") for argument in before["CompileCommand"]]
        after_command = [argument.replace(after["BuildDirectory"], "BUILD") for argument in after["CompileCommand"]]
        if before_command != after_command:
            raise ValueError("Compile command differs beyond isolated build paths")
        if before["SourceSnapshot"].keys() != after["SourceSnapshot"].keys():
            raise ValueError("Source list differs")
        changed = [name for name in before["SourceSnapshot"] if before["SourceSnapshot"][name] != after["SourceSnapshot"][name]]
        if set(changed) != {"rtl/rv32_core.sv"}:
            raise ValueError("Unexpected simulation input changes")
        for name, expected in after["SourceSnapshot"].items():
            if digest(ROOT / name) != expected:
                raise ValueError("Current candidate no longer matches " + name)
        if any(reference[key] != candidate[key] for key in ("retired", "profile", "seed_crc", "final_crc", "validation_run", "clock_hz")):
            raise ValueError("Observable benchmark behavior differs beyond cycles")
        if candidate["validation_run"] != bool(validation) or candidate["cycles"] != reference["cycles"]:
            raise ValueError("Wrong validation seed or changed cycle count")
        receipt["pairs"].append({"validation": bool(validation), "baseline_build": before_id,
            "candidate_build": after_id, "baseline_cycles": reference["cycles"], "candidate_cycles": candidate["cycles"],
            "cycles_saved": reference["cycles"] - candidate["cycles"], "retired": candidate["retired"],
            "cycle_reduction_percent": 100 * (1 - candidate["cycles"] / reference["cycles"]),
            "throughput_improvement_percent": 100 * (reference["cycles"] / candidate["cycles"] - 1),
            "baseline_manifest_sha256": digest(before_path / "manifest.json"),
            "candidate_manifest_sha256": digest(after_path / "manifest.json"), "changed_inputs": changed})
    destination = ROOT / "build/short-comparison.json"
    text = json.dumps(receipt, indent=2) + "\n"
    if destination.exists() and destination.read_text() != text:
        raise ValueError("Refusing to overwrite different comparison")
    destination.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

