import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from run_coremark_compiled import check_simulation_result, verify_artifacts


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_run(directory, iterations=10):
    require(iterations in (10, 6000), "Unsupported comparison duration")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
    require(manifest["SimulationPassed"], "Simulation not passed")
    verify_artifacts(directory, manifest)
    for filename, key in (("coremark.sim.uart", "UartSha256"), ("result.json", "ResultSha256")):
        require(digest(directory / filename) == manifest[key], "Output changed: " + filename)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    parsed = check_simulation_result((directory / "coremark.sim.uart").read_text(encoding="utf-8"),
                                     manifest["FirmwareBuild"], manifest["HardwareParameters"], iterations == 10)
    require(result == parsed, "Stored result differs from parsed UART")
    require(result["crc_valid"] and result["iterations"] == iterations, "Wrong run duration or CRC")
    if iterations == 6000:
        require(manifest.get("CompletedUtc") and result["modeled_duration_at_least_10s"], "Incomplete long duration evidence")
    require(manifest["FirmwareBuild"]["HexSha256"] == manifest["FirmwareSha256"], "Firmware manifest hash mismatch")
    return manifest, result



def main():
    from audit_clock import audit_sources, validate_firmware
    configuration = audit_sources()
    runs = json.loads((ROOT / "short-runs.json").read_text(encoding="utf-8"))
    require(set(runs) == {"performance", "validation"}, "Incomplete short pair")
    baseline = ROOT.parent / "full_redirect_prime/build/compiled"
    references = ("20260910-221841-e6c87093", "20260910-221854-55aa843e")
    receipt = {"schema": 1, "scope": "clock-specific short RTL screen, not a long-run or hardware score", "pairs": []}
    for validation, name in enumerate(("performance", "validation")):
        after_path = ROOT / "build/compiled" / runs[name]
        before_path = baseline / references[validation]
        before, reference = read_run(before_path)
        after, candidate = read_run(after_path)
        validate_firmware(after["FirmwareBuild"], bool(validation), 10)
        require(after["ConfigurationInput"] == configuration, "Wrong captured configuration")
        require(before["HardwareParameters"] == after["HardwareParameters"], "Hardware parameters changed")
        require(before["SourceSnapshot"] == after["SourceSnapshot"], "Simulation sources changed")
        for relative, expected in after["SourceSnapshot"].items():
            require(digest(ROOT / relative) == expected, "Current simulation source changed: " + relative)
        for field in ("SimulationBackend", "SimulationClockHz", "UartModelClockHz"):
            require(before[field] == after[field], "Simulation backend differs: " + field)
        before_command = [value.replace(before["BuildDirectory"], "BUILD") for value in before["CompileCommand"]]
        after_command = [value.replace(after["BuildDirectory"], "BUILD") for value in after["CompileCommand"]]
        require(before_command == after_command, "Compile commands differ")
        for field in ("cycles", "retired", "seed_crc", "final_crc", "validation_run", "profile"):
            require(reference[field] == candidate[field], "Benchmark behavior differs: " + field)
        require(reference["clock_hz"] == 154285714 and candidate["clock_hz"] == 151200000, "Wrong clock pair")
        before_firmware = before["FirmwareBuild"]
        after_firmware = after["FirmwareBuild"]
        changed_fields = {"Flags", "ClockHz", "Hex", "RunName", "HexSha256"}
        require(set(before_firmware) == set(after_firmware), "Firmware metadata fields differ")
        for field in before_firmware.keys() - changed_fields:
            require(before_firmware[field] == after_firmware[field], "Firmware settings changed: " + field)
        require([flag.replace("-DCPU_CLOCK_HZ=154285714u", "-DCPU_CLOCK_HZ=151200000u") for flag in before_firmware["Flags"]] == after_firmware["Flags"], "Non-clock compiler flag change")
        receipt["pairs"].append({"validation": bool(validation), "parent_build": references[validation], "candidate_build": runs[name], "cycles": candidate["cycles"], "retired": candidate["retired"], "clock_hz": candidate["clock_hz"], "source_files_unchanged": True, "parent_manifest_sha256": digest(before_path / "manifest.json"), "candidate_manifest_sha256": digest(after_path / "manifest.json")})
    destination = ROOT / "build/short-comparison.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite changed comparison")
    destination.write_text(text, encoding="utf-8")
    print(text)
    return receipt


if __name__ == "__main__":
    main()
