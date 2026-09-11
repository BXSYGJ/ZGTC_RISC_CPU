import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import run_fetch_profile as runner
from audit_fetch_inputs import ROOT, digest, require, load
from audit_fetch_long import portable
from load_use_profile import extract_cycle_pc, firmware_image


def audit(directory):
    directory = directory.resolve()
    require(directory.parent == (ROOT / "build/retirement-profile").resolve(), "Wrong profile workspace")
    runner.short_audit.audit_shorts()
    record = load(directory / "invocation.json")
    require(record.get("passed") is True and record.get("hardware_validated") is False and record.get("unchanged_uart") is True, "Profile incomplete or mislabeled")
    require(type(record["validation_run"]) is bool, "Invalid profile role")
    require(record["runner_sha256"] == digest(ROOT / "run_fetch_profile.py") and record["observer_sha256"] == digest(runner.DRIVER) == runner.DRIVER_SHA256, "Profiler or observer changed")
    libraries = {name: digest(runner.CPU / "scripts" / name) for name in ("load_use_profile.py", "retirement_gap_profile.py")}
    require(record["library_sha256"] == libraries, "Profile analysis library changed")
    baseline = ROOT / "build/compiled" / runner.BASELINES[record["validation_run"]]
    require(record["baseline"] == baseline.name and digest(baseline / "manifest.json") == record["baseline_manifest_sha256"], "Profile baseline differs")
    original = load(baseline / "manifest.json")
    build = (directory / record["build"]).resolve()
    require(build.parent == (directory / "stage/build/compiled").resolve(), "Profile build outside captured stage")
    manifest = load(build / "manifest.json")
    require(digest(build / "manifest.json") == record["profile_manifest_sha256"], "Profile manifest changed")
    expected_compile = [argument.replace(portable(baseline), portable(build)) for argument in original["CompileCommand"]]
    require(manifest["CompileCommand"] == expected_compile, "Profile compiler command changed")
    require(manifest["SimulationBackend"] == original["SimulationBackend"] and portable(manifest["BuildDirectory"]) == portable(build), "Wrong profile simulator or build identity")
    started, completed = (datetime.fromisoformat(manifest[name]) for name in ("StartedUtc", "CompletedUtc"))
    require(started.utcoffset() is not None and completed.utcoffset() is not None and completed >= started, "Invalid profile simulation interval")
    log_text = (build / "simulation.log").read_text(encoding="utf-8")
    require(len(re.findall(r"^PASS compiled RTL simulation cycles=\d+ retired=\d+$", log_text, re.M)) == 1 and not re.search(r"FAIL|FATAL|watchdog", log_text, re.I), "Profile terminal result missing or failed")
    firmware = original["FirmwareBuild"]
    name = firmware["RunName"]
    parent = runner.short_audit.inputs.PARENT / "build"
    image_path, elf, firmware_manifest = (parent / (name + suffix) for suffix in (".hex", ".elf", ".build.json"))
    image = firmware_image(image_path)
    require(record["firmware_sha256"] == digest(image_path) and record["elf_sha256"] == digest(elf), "Profile firmware or ELF changed")
    require((directory / "firmware.bin").read_bytes().ljust(len(image), b"\0") == image, "Profile ELF export differs from loaded image")
    boundaries = {function: extract_cycle_pc((directory / (function + ".disassembly.txt")).read_text(encoding="utf-8"), image, function) for function in ("start_time", "stop_time")}
    require(record["boundaries"] == boundaries and boundaries["start_time"] != boundaries["stop_time"], "Profile ELF boundaries differ")
    prefix = firmware["Toolchain"]["Prefix"]
    commands = [[prefix + "gcc", "-dumpmachine"], [prefix + "gcc", "-dumpfullversion"],
                [prefix + "objcopy", "-O", "binary", portable(elf), portable(directory / "firmware.bin")],
                *[[prefix + "objdump", "-d", "--disassemble=" + function, portable(elf)] for function in ("start_time", "stop_time")],
                ["/usr/bin/env", f"ZGTC_TRACE_START_PC={boundaries['start_time']:x}", f"ZGTC_TRACE_STOP_PC={boundaries['stop_time']:x}",
                 "/usr/bin/python3", portable(directory / "stage/scripts/run_coremark_compiled.py"), "--configuration", portable(directory / "configuration.json"),
                 "--firmware-manifest", portable(firmware_manifest), "--allow-short", "--max-cycles", "10000000"]]
    require(record["commands"] == [["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", *command] for command in commands], "Profile invocation commands changed")
    require(load(directory / "configuration.json") == original["ConfigurationInput"], "Profile configuration file differs")
    expected_files = {"configuration.json", "compiler-target.log", "compiler-version.log", "objcopy.log", "firmware.bin", "start_time.disassembly.txt", "stop_time.disassembly.txt", "profile-run.log", "retirement-gaps.json"}
    require(set(record["evidence_outputs"]) == expected_files, "Incomplete profile evidence inventory")
    for relative, checksum in record["evidence_outputs"].items():
        require(digest(directory / relative) == checksum, "Profile evidence changed: " + relative)
    require(digest(build / "coremark.sim.uart.retire.bin") == record["trace_sha256"] and digest(build / "coremark.sim.uart.retire.json") == record["trace_metadata_sha256"], "Profile trace changed")
    result, metadata, summary = runner.validate_profile(build, baseline, boundaries, image)
    require(result == record["result"] and metadata == record["metadata"], "Stored profile metadata differs from raw trace")
    normalized = json.loads(json.dumps(summary))
    require(normalized == load(directory / "retirement-gaps.json") and digest(directory / "retirement-gaps.json") == record["summary_sha256"], "Stored gap summary differs from trace")
    return {"scope": "source-bound nonintrusive short retirement-gap observations; not internal stall attribution, long score or hardware evidence",
            "passed": True, "validation_run": record["validation_run"], "directory": str(directory), "invocation_sha256": digest(directory / "invocation.json"),
            "records": summary["records"], "cycles": summary["cycles"], "extra_cycles_above_one_per_interval": summary["extra_cycles_above_one_per_interval"],
            "axes": summary["axes"], "hardware_validated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2))
