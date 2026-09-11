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
    baseline = ROOT.parent / "full_redirect_prime/build/compiled"
    builds = (("20260910-221841-e6c87093", "20260910-230309-3456598d"),
              ("20260910-221854-55aa843e", "20260910-230321-0d85a2ff"))
    receipt = {"schema": 1, "scope": "matching-clock short RTL validation, not official or hardware scores", "pairs": []}
    for validation, (before_id, after_id) in enumerate(builds):
        before_path = baseline / before_id
        after_path = ROOT / "build/compiled" / after_id
        before, reference = read_run(before_path)
        after, candidate = read_run(after_path)
        require(before["HardwareParameters"] == after["HardwareParameters"], "Hardware parameters differ")
        require(before["SimulationBackend"] == after["SimulationBackend"], "Backend differs")
        for field in ("SimulationClockHz", "UartModelClockHz"):
            require(before[field] == after[field], "Simulation model clock differs")
        before_command = [argument.replace(before["BuildDirectory"], "BUILD") for argument in before["CompileCommand"]]
        after_command = [argument.replace(after["BuildDirectory"], "BUILD") for argument in after["CompileCommand"]]
        require(before_command == after_command, "Compile commands differ beyond build paths")
        require(before["SourceSnapshot"].keys() == after["SourceSnapshot"].keys(), "Source list differs")
        changed = [name for name in before["SourceSnapshot"] if before["SourceSnapshot"][name] != after["SourceSnapshot"][name]]
        require(changed == ["rtl/rv32_core.sv"], "Unexpected simulation source change")
        for relative, expected in after["SourceSnapshot"].items():
            require(digest(ROOT / relative) == expected, "Current source changed: " + relative)
        for key in ("retired", "seed_crc", "final_crc", "validation_run"):
            require(reference[key] == candidate[key], "Benchmark behavior differs: " + key)
        require(candidate == reference, "Structural change altered short-run behavior")
        require(before["FirmwareBuild"] == after["FirmwareBuild"], "Firmware metadata changed")
        require(before["FirmwareSha256"] == after["FirmwareSha256"], "Firmware bytes changed")
        require(after["ConfigurationInput"]["HistoryBits"] == 3, "Wrong history metadata")
        delta = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
        expected_core = (before_path / "source/rtl/rv32_core.sv").read_text(encoding="utf-8")
        for old, new in delta["substitutions"]:
            require(expected_core.count(old) == 1, "Ambiguous core substitution")
            expected_core = expected_core.replace(old, new)
        require(expected_core == (after_path / "source/rtl/rv32_core.sv").read_text(encoding="utf-8"), "Unexpected CPU delta")
        require(candidate["validation_run"] == bool(validation), "Wrong validation seed")
        require(reference["clock_hz"] == 154285714 and candidate["clock_hz"] == 154285714, "Wrong clock pair")
        before_firmware = before["FirmwareBuild"]
        after_firmware = after["FirmwareBuild"]
        for key in ("UpstreamRevision", "Iterations", "ValidationRun", "Toolchain", "Optimization", "UnrollLoops",
                    "LinkTimeOptimization", "LinkerRelaxation", "ConsoleDelayCycles", "Isa", "EnableM", "ExtraLinkFlags"):
            require(before_firmware[key] == after_firmware[key], "Firmware settings differ: " + key)
        normalized_flags = [flag.replace("-DCPU_CLOCK_HZ=157500000u", "-DCPU_CLOCK_HZ=154285714u") for flag in before_firmware["Flags"]]
        require(normalized_flags == after_firmware["Flags"], "Firmware flags differ beyond clock")
        receipt["pairs"].append({"validation": bool(validation), "parent_build": before_id, "candidate_build": after_id,
            "parent_cycles": reference["cycles"], "cycles_saved": reference["cycles"] - candidate["cycles"],
            "throughput_ratio": reference["cycles"] / candidate["cycles"],
            "cycles": candidate["cycles"], "retired": candidate["retired"], "clock_hz": candidate["clock_hz"],
            "parent_manifest_sha256": digest(before_path / "manifest.json"),
            "candidate_manifest_sha256": digest(after_path / "manifest.json"), "changed_simulation_inputs": changed})
    destination = ROOT / "build/short-comparison.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite different comparison")
    destination.write_text(text, encoding="utf-8")
    print(text)
    return receipt


if __name__ == "__main__":
    main()


