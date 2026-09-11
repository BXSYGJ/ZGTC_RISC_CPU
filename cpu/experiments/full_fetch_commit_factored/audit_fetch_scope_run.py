import argparse
import json
from datetime import datetime
from pathlib import Path

import run_fetch_scope as runner
from audit_fetch_scope_firmware import audit_firmware
from audit_fetch_inputs import ROOT, digest, require, load
from build_scope_firmware import NAME


def audit(directory):
    directory = directory.resolve()
    require(directory.parent == (ROOT / "build/scope-current").resolve(), "Unexpected application workspace")
    record = load(directory / "manifest.json")
    require(record.get("passed") is True and record.get("hardware_validated") is False, "Application simulation incomplete or mislabeled")
    require(record["host_timeout_seconds"] == 1800 and record["simulation_overrides"] == runner.OVERRIDES, "Application model overrides changed")
    require(record["runner_sha256"] == digest(ROOT / "run_fetch_scope.py") and record["support_hashes"] == runner.validate_support(), "Application runner or support changed")
    firmware = audit_firmware(directory / "firmware.hex")
    require(record["firmware_sha256"] == firmware["firmware_sha256"] and record["firmware_metadata"] == load(ROOT / "build" / (NAME + ".build.json")), "Application firmware metadata changed")
    bound = runner.physical.binding()
    parameters = bound["hardware_parameters"]
    require(record["physical_parameters"] == dict(parameters, CLOCK_HZ=153000000, UART_BAUD=115200), "Wrong application CPU parameters")
    snapshot = load(runner.physical.SOURCE / "source-snapshot.json")
    require(record["source_snapshot"] == snapshot, "Application physical snapshot differs")
    expected_inputs = {relative for relative in snapshot["Files"] if relative.startswith("rtl/")} | {"scope_tb.sv"}
    require(set(record["input_hashes"]) == expected_inputs, "Application input inventory incomplete")
    for relative, checksum in record["input_hashes"].items():
        require(digest(directory / relative) == checksum, "Captured application input changed: " + relative)
        if relative.startswith("rtl/"):
            require(checksum == snapshot["Files"][relative] == digest(ROOT / relative) == digest(runner.physical.SOURCE / "source" / relative), "Application RTL differs from physical source")
    require((directory / "scope_tb.sv").read_text(encoding="utf-8") == runner.generate_bench(parameters), "Compiled scope bench differs from declared model")
    sources = sorted((directory / "rtl").glob("*.sv")) + [directory / "scope_tb.sv"]
    expected_commands = [["iverilog", "-g2012", "-Wall", "-s", "scope_tb", "-o", str(directory / "scope.vvp"), *map(str, sources)],
                         ["vvp", "-i", str(directory / "scope.vvp"), "+firmware=" + str(directory / "firmware.hex"), "+uart=" + str(directory / "scope.uart")]]
    require(record["commands"] == expected_commands, "Application compile or execution command differs")
    output_names = {"scope.uart", "execute.log", "compile.log", "scope.vvp", "capture-0.svg", "capture-1.svg"}
    require(set(record["outputs_sha256"]) == output_names, "Incomplete application output inventory")
    started, finished = (datetime.fromisoformat(record[name]) for name in ("started_utc", "completed_utc"))
    require(started.utcoffset() is not None and finished.utcoffset() is not None and finished >= started, "Invalid application invocation interval")
    for name, checksum in record["outputs_sha256"].items():
        path = directory / name
        require(digest(path) == checksum and started.timestamp() - 2 <= path.stat().st_mtime <= finished.timestamp() + 2, "Application output changed or outside invocation: " + name)
    cycles, captures = runner.validate_output((directory / "execute.log").read_text(encoding="utf-8"), (directory / "scope.uart").read_text(encoding="utf-8"))
    require(record["cycles"] == cycles and 0 < cycles <= 10000000, "Application terminal cycle count differs")
    summaries = [{key: value for key, value in capture.items() if key != "records"} for capture in captures]
    require(record["captures"] == summaries, "Application summary differs from raw UART")
    for index, capture in enumerate(captures):
        require((directory / f"capture-{index}.svg").read_text(encoding="utf-8") == runner.decoder.waveform_svg(capture), "Application waveform differs from raw samples")
    return {"scope": "source-bound full-CPU application RTL simulation, not physical, board or CDC qualification", "simulation_passed": True,
            "cycles": cycles, "captures": summaries, "firmware": firmware, "manifest_sha256": digest(directory / "manifest.json"),
            "counter_jumps_used": runner.OVERRIDES["timeout_counter_jumps"], "timeout_test_kind": "bounded 64-bit counter jumps, not 30 seconds of continuous simulation",
            "hardware_validated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = audit(args.directory)
    print(json.dumps(result, indent=2))
