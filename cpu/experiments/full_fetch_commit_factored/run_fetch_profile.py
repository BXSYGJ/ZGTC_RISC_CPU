import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import audit_fetch_shorts as short_audit
from audit_fetch_inputs import ROOT, digest, require, load
from audit_fetch_long import portable
from load_use_profile import DRIVER_SHA256, extract_cycle_pc, firmware_image, trace_records
from retirement_gap_profile import summarize_records

CPU = ROOT.parents[1]
DRIVER = CPU / "experiments/load_use_profile/coremark_compiled.cpp"
BASELINES = {False: "20260911-094801-420d3685", True: "20260911-094810-8ee47390"}


def validate_profile(build, baseline, boundaries, image):
    original, manifest = load(baseline / "manifest.json"), load(build / "manifest.json")
    require(manifest["SimulationPassed"] is True and manifest["MeasurementKind"] == "rtl_simulation_not_hardware", "Profile simulation incomplete or mislabeled")
    for relative, checksum in manifest["SourceSnapshot"].items():
        require(digest(build / "source" / relative) == checksum, "Captured profile source changed")
    require(digest(build / "firmware.hex") == manifest["FirmwareSha256"] and digest(build / "objects/Vrv32_soc") == manifest["ExecutableSha256"], "Profile firmware or executable changed")
    expected = dict(original["SourceSnapshot"])
    expected["sim/coremark_compiled.cpp"] = DRIVER_SHA256
    require(manifest["SourceSnapshot"] == expected, "Observer changed non-observer sources")
    require(manifest["ConfigurationInput"] == original["ConfigurationInput"] and manifest["HardwareParameters"] == original["HardwareParameters"], "Observer changed CPU configuration")
    require(manifest["FirmwareBuild"] == original["FirmwareBuild"] and manifest["FirmwareSha256"] == original["FirmwareSha256"], "Observer changed firmware")
    require(manifest["FirmwareBuild"]["Iterations"] == 10 and manifest["MaxCycles"] == 10000000, "Profile scope must remain ten iterations")
    require(manifest["SimulationClockHz"] == original["SimulationClockHz"] and manifest["UartModelClockHz"] == original["UartModelClockHz"], "Observer changed clock models")
    require((build / "coremark.sim.uart").read_bytes() == (baseline / "coremark.sim.uart").read_bytes(), "Observer changed raw UART")
    result = load(baseline / "result.json")
    require(result == load(build / "result.json"), "Observer changed cycles, counters or CRC")
    require(digest(build / "coremark.sim.uart") == manifest["UartSha256"] and digest(build / "result.json") == manifest["ResultSha256"], "Profile result hashes differ")
    metadata = load(build / "coremark.sim.uart.retire.json")
    require(metadata["start_pc"] == boundaries["start_time"] and metadata["stop_pc"] == boundaries["stop_time"], "Trace timer boundaries differ")
    require(metadata["cycles"] == result["cycles"], "Trace cycle span differs from benchmark interval")
    summary = summarize_records(trace_records(build / "coremark.sim.uart.retire.bin", metadata, image))
    require(summary["records"] == metadata["records"] and summary["cycles"] == metadata["cycles"], "Trace summary fails conservation")
    return result, metadata, summary


def main(validation=False):
    require(type(validation) is bool, "Invalid profile seed")
    short_audit.audit_shorts()
    require(digest(DRIVER) == DRIVER_SHA256, "Existing nonintrusive observer changed")
    baseline = ROOT / "build/compiled" / BASELINES[validation]
    original = load(baseline / "manifest.json")
    firmware = original["FirmwareBuild"]
    name = firmware["RunName"]
    firmware_root = short_audit.inputs.PARENT / "build"
    manifest_path = firmware_root / (name + ".build.json")
    require(load(manifest_path) == firmware and firmware["Iterations"] == 10, "Wrong profile firmware")
    image_path, elf = firmware_root / (name + ".hex"), firmware_root / (name + ".elf")
    image = firmware_image(image_path)
    directory = ROOT / "build/retirement-profile" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    stage = directory / "stage"
    stage.mkdir(parents=True, exist_ok=False)
    record = {"schema": 1, "scope": "ten-iteration nonintrusive retirement-gap profile, not a score or internal stall attribution", "passed": False,
              "started_utc": datetime.now(timezone.utc).isoformat(), "validation_run": validation, "baseline": BASELINES[validation],
              "baseline_manifest_sha256": digest(baseline / "manifest.json"), "runner_sha256": digest(Path(__file__)), "observer_sha256": DRIVER_SHA256,
              "library_sha256": {name: digest(CPU / "scripts" / name) for name in ("load_use_profile.py", "retirement_gap_profile.py")}, "commands": []}
    receipt = directory / "invocation.json"
    def execute(command, log_name, timeout=300):
        native = ["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", *command]
        record["commands"].append(native)
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        with (directory / log_name).open("w", encoding="utf-8") as output:
            completed = subprocess.run(native, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
        require(completed.returncode == 0, "Profile command failed: " + log_name)
        return (directory / log_name).read_text(encoding="utf-8")
    print("RETIREMENT_PROFILE=" + directory.as_posix(), flush=True)
    for relative, checksum in original["SourceSnapshot"].items():
        origin = DRIVER if relative == "sim/coremark_compiled.cpp" else baseline / "source" / relative
        expected = DRIVER_SHA256 if relative == "sim/coremark_compiled.cpp" else checksum
        require(digest(origin) == expected, "Profile staging source differs: " + relative)
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, destination)
    configuration = directory / "configuration.json"
    configuration.write_text(json.dumps(original["ConfigurationInput"], indent=2) + "\n", encoding="utf-8")
    prefix = firmware["Toolchain"]["Prefix"]
    require(execute([prefix + "gcc", "-dumpmachine"], "compiler-target.log").strip() == firmware["Toolchain"]["Target"] == "riscv32-unknown-elf", "Profile toolchain target differs")
    require(execute([prefix + "gcc", "-dumpfullversion"], "compiler-version.log").strip() == firmware["Toolchain"]["Version"] == "10.2.0", "Profile toolchain version differs")
    binary = directory / "firmware.bin"
    execute([prefix + "objcopy", "-O", "binary", portable(elf), portable(binary)], "objcopy.log")
    require(binary.read_bytes().ljust(len(image), b"\0") == image, "Profile ELF differs from loaded firmware")
    boundaries = {}
    for function in ("start_time", "stop_time"):
        disassembly = execute([prefix + "objdump", "-d", "--disassemble=" + function, portable(elf)], function + ".disassembly.txt")
        boundaries[function] = extract_cycle_pc(disassembly, image, function)
    require(boundaries["start_time"] != boundaries["stop_time"], "Profile boundaries must differ")
    record["boundaries"] = boundaries
    execute(["/usr/bin/env", f"ZGTC_TRACE_START_PC={boundaries['start_time']:x}", f"ZGTC_TRACE_STOP_PC={boundaries['stop_time']:x}",
             "/usr/bin/python3", portable(stage / "scripts/run_coremark_compiled.py"), "--configuration", portable(configuration),
             "--firmware-manifest", portable(manifest_path), "--allow-short", "--max-cycles", "10000000"], "profile-run.log", 600)
    builds = list((stage / "build/compiled").glob("*/manifest.json"))
    require(len(builds) == 1, "Missing or ambiguous profile build")
    build = builds[0].parent
    result, metadata, summary = validate_profile(build, baseline, boundaries, image)
    short_audit.audit_shorts()
    require(record["runner_sha256"] == digest(Path(__file__)) and digest(DRIVER) == DRIVER_SHA256, "Profiler source changed during execution")
    summary_path = directory / "retirement-gaps.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    record.update(passed=True, completed_utc=datetime.now(timezone.utc).isoformat(), build=build.relative_to(directory).as_posix(),
                  result=result, metadata=metadata, profile_manifest_sha256=digest(build / "manifest.json"),
                  trace_sha256=digest(build / "coremark.sim.uart.retire.bin"), trace_metadata_sha256=digest(build / "coremark.sim.uart.retire.json"),
                  summary_sha256=digest(summary_path), firmware_sha256=digest(image_path), elf_sha256=digest(elf),
                  unchanged_uart=True, hardware_validated=False,
                  evidence_outputs={path.name: digest(path) for path in directory.iterdir() if path.is_file() and path != receipt})
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "directory": str(directory), "records": summary["records"], "cycles": summary["cycles"],
                      "extra_cycles_above_one_per_interval": summary["extra_cycles_above_one_per_interval"], "axes": summary["axes"],
                      "top_transitions": summary["transitions"][:12], "hardware_validated": False}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation", action="store_true")
    args = parser.parse_args()
    main(args.validation)
