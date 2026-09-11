import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

STAGE = Path(__file__).resolve().parent
CPU = STAGE.parents[1]
sys.path.insert(0, str(STAGE / "scripts"))
from run_coremark_compiled import check_simulation_result, verify_artifacts


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    baseline_path = CPU / "build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    require(baseline["coremark_pair_hardware_passed"], "Baseline pair is not qualified")
    receipt = {"schema": 1, "scope": "source-bound long RTL counters and conditional clock planning; not hardware or official scores",
               "baseline_receipt_sha256": digest(baseline_path), "hardware_validated": False, "full_score_qualified": False, "runs": []}
    build_ids = ("20260910-191854-9844bd02", "20260910-191917-c43b70ee")
    for validation, build_id in enumerate(build_ids):
        directory = STAGE / "build/compiled" / build_id
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
        require(manifest["SimulationPassed"] and manifest.get("CompletedUtc"), "Simulation not complete")
        verify_artifacts(directory, manifest)
        for relative, expected in manifest["SourceSnapshot"].items():
            require(digest(STAGE / relative) == expected, "Current source differs: " + relative)
        for filename, key in (("coremark.sim.uart", "UartSha256"), ("result.json", "ResultSha256")):
            require(digest(directory / filename) == manifest[key], "Output changed: " + filename)
        result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        parsed = check_simulation_result((directory / "coremark.sim.uart").read_text(encoding="utf-8"),
                                        manifest["FirmwareBuild"], manifest["HardwareParameters"], False)
        require(parsed == result, "Stored result differs from actual UART")
        require(result["iterations"] == 6000 and result["validation_run"] == bool(validation), "Wrong seed or iterations")
        require(result["clock_hz"] == 157500000 and result["modeled_duration_at_least_10s"], "Wrong clock or duration")
        reference_run = next(run for run in baseline["runs"] if run["result"]["validation_run"] == bool(validation))
        reference = reference_run["result"]
        require(manifest["FirmwareSha256"].lower() == reference_run["physical"]["artifacts_sha256"]["firmware.hex"].lower(), "Firmware differs from baseline")
        for key in ("iterations", "retired", "seed_crc", "final_crc", "profile"):
            require(result[key] == reference[key], "Benchmark behavior differs: " + key)
        require(result["cycles"] < reference["cycles"], "No cycle improvement")
        floor = Fraction(reference["clock_hz"] * result["cycles"], reference["cycles"])
        receipt["runs"].append({"build": build_id, "validation_run": bool(validation), "cycles": result["cycles"],
            "baseline_cycles": reference["cycles"], "cycles_saved": reference["cycles"] - result["cycles"],
            "retired": result["retired"], "execution_efficiency_from_rtl_counters": float(Fraction(6000000000, result["cycles"])),
            "conditional_clock_floor_for_same_seed_baseline_hz_exact": str(floor),
            "conditional_clock_floor_for_same_seed_baseline_hz": float(floor),
            "manifest_sha256": digest(directory / "manifest.json"), "result_sha256": digest(directory / "result.json")})
    destination = STAGE / "build/long-counter-audit.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite different long audit")
    destination.write_text(text, encoding="utf-8")
    print(text)
    return receipt


if __name__ == "__main__":
    main()
