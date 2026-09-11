import argparse
import json
from pathlib import Path

from audit_short import ROOT, digest, read_run, require

PARENT_RUNS = ("20260910-200328-351ec921", "20260910-200355-357efcf4")


def compare(parent_directory, candidate_directory, validation):
    before, reference = read_run(parent_directory, 6000)
    after, result = read_run(candidate_directory, 6000)
    from audit_clock import audit_sources, validate_firmware
    configuration = audit_sources()
    require(after["ConfigurationInput"] == configuration, "Wrong captured long configuration")
    validate_firmware(after["FirmwareBuild"], validation, 6000)
    for key in ("HardwareParameters", "SimulationBackend", "SimulationClockHz", "UartModelClockHz"):
        require(before[key] == after[key], "Long-run settings differ: " + key)
    before_command = [argument.replace(before["BuildDirectory"], "BUILD") for argument in before["CompileCommand"]]
    after_command = [argument.replace(after["BuildDirectory"], "BUILD") for argument in after["CompileCommand"]]
    require(before_command == after_command, "Long compilation commands differ")
    require(before["SourceSnapshot"].keys() == after["SourceSnapshot"].keys(), "Long source sets differ")
    changed = [name for name in before["SourceSnapshot"] if before["SourceSnapshot"][name] != after["SourceSnapshot"][name]]
    require(changed == ["rtl/rv32_core.sv"], "Unexpected long source change")
    delta = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
    for relative, expected in delta["source_hashes"].items():
        require(digest(ROOT / relative) == expected, "Current physical source changed: " + relative)
    for relative, expected in after["SourceSnapshot"].items():
        require(digest(ROOT / relative) == expected, "Current simulation source changed: " + relative)
        if relative.startswith("rtl/"):
            require(delta["source_hashes"][relative] == expected, "Long RTL not bound to candidate: " + relative)
    expected_core = (parent_directory / "source/rtl/rv32_core.sv").read_text(encoding="utf-8")
    prime_delta = json.loads((ROOT.parent / "full_redirect_prime/source-inputs.json").read_text(encoding="utf-8"))
    require(before["SourceSnapshot"]["rtl/rv32_core.sv"] == prime_delta["parent_hashes"]["rtl/rv32_core.sv"], "Wrong long reference CPU")
    require(delta["source_hashes"]["rtl/rv32_core.sv"] == prime_delta["source_hashes"]["rtl/rv32_core.sv"], "CPU delta chain mismatch")
    for old, new in prime_delta["substitutions"]:
        require(expected_core.count(old) == 1, "Ambiguous long source substitution")
        expected_core = expected_core.replace(old, new)
    require(expected_core == (candidate_directory / "source/rtl/rv32_core.sv").read_text(encoding="utf-8"), "Unexpected long CPU delta")
    for key in ("retired", "seed_crc", "final_crc", "validation_run"):
        require(reference[key] == result[key], "Long behavior differs: " + key)
    require(result["validation_run"] is validation, "Wrong long validation seed")
    require(reference["clock_hz"] == 154285714 and result["clock_hz"] == 151200000, "Wrong long configured clock pair")
    before_firmware, after_firmware = before["FirmwareBuild"], after["FirmwareBuild"]
    changed_fields = {"Flags", "ClockHz", "Hex", "RunName", "HexSha256"}
    require(set(before_firmware) == set(after_firmware), "Firmware metadata fields differ")
    for field in before_firmware.keys() - changed_fields:
        require(before_firmware[field] == after_firmware[field], "Long firmware setting changed: " + field)
    require([flag.replace("-DCPU_CLOCK_HZ=154285714u", "-DCPU_CLOCK_HZ=151200000u") for flag in before_firmware["Flags"]] == after_firmware["Flags"], "Non-clock long compiler flag change")
    return {"validation": validation, "parent_build": parent_directory.name, "candidate_build": candidate_directory.name,
            "parent_cycles": reference["cycles"], "cycles": result["cycles"],
            "cycles_saved": reference["cycles"] - result["cycles"], "execution_efficiency_ratio": reference["cycles"] / result["cycles"],
            "modeled_throughput_ratio": (result["clock_hz"] / reference["clock_hz"]) * reference["cycles"] / result["cycles"],
            "retired": result["retired"], "crc_valid": result["crc_valid"], "final_crc": result["final_crc"],
            "modeled_seconds": result["seconds"], "modeled_execution_efficiency": result["iterations"] * 1000000 / result["cycles"],
            "modeled_iterations_per_second": result["iterations"] * result["clock_hz"] / result["cycles"],
            "parent_manifest_sha256": digest(parent_directory / "manifest.json"),
            "candidate_manifest_sha256": digest(candidate_directory / "manifest.json")}


def audit(performance, validation):
    directories = (performance.resolve(), validation.resolve())
    workspace = (ROOT / "build/compiled").resolve()
    for directory in directories:
        require(directory.parent == workspace, "Unexpected compiled workspace")
    pairs = [compare(ROOT.parent / "full_control_commit/build/compiled" / parent_run, directory, bool(index))
             for index, (parent_run, directory) in enumerate(zip(PARENT_RUNS, directories))]
    receipt = {"schema": 1, "scope": "matched paired 6000-iteration RTL execution screen; not timing or hardware qualification",
               "pairs": pairs, "physical_timing_qualified": False, "resource_efficiency_qualified": False,
               "hardware_validated": False, "baseline_replaced": False}
    destination = ROOT / "build/long-comparison.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to replace different long comparison")
    destination.write_text(text, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.performance, arguments.validation), indent=2))


