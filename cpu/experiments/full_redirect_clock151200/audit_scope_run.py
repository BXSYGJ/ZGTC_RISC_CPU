import argparse
import json
import re
from pathlib import Path

from audit_clock import audit_sources
from audit_scope_firmware import audit as audit_firmware
from audit_short import ROOT, digest, require
from scripts.scope_decode import parse_captures, decode_triggered_uart, transitions


def audit(directory):
    directory = directory.resolve()
    require(directory.parent == (ROOT / "build/scope-current").resolve(), "Unexpected application workspace")
    configuration = audit_sources()
    record = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    require(record.get("passed") is True and record.get("hardware_validated") is False, "Application simulation is incomplete or mislabeled")
    require(record.get("host_timeout_seconds") == 1800, "Unexpected scope host timeout budget")
    require(digest(ROOT / "run_scope_current.py") == record["runner_sha256"], "Scope runner changed")
    require(digest(ROOT / "scripts/scope_decode.py") == record["decoder_sha256"], "Scope decoder changed")
    firmware = audit_firmware(directory / "firmware.hex")
    require(firmware["firmware_sha256"] == record["firmware_sha256"], "Scope firmware binding changed")
    expected_metadata = json.loads((ROOT / "build/scope_p0_s1210_t4536000000_rv32gcc_f151200000.build.json").read_text(encoding="utf-8-sig"))
    require(record["firmware_metadata"] == expected_metadata, "Scope firmware metadata differs")
    expected_overrides = {"CLOCK_HZ": 3200, "BAUD": 100, "clock_period_ns": 10, "uart_injected_bit_cycles": 15750,
                          "key_pulse_cycles": 44800, "timeout_counter_jumps": [4294967296, 241032704]}
    require(record["simulation_overrides"] == expected_overrides, "Scope stimulus or counter jumps changed")
    from audit_binding import hardware_parameters
    expected_parameters = dict(hardware_parameters(configuration), CLOCK_HZ=151200000, UART_BAUD=115200)
    require(record["physical_parameters"] == expected_parameters, "Wrong application hardware configuration")
    physical = ROOT / "build/pds/20260910-233603-e3b63565"
    snapshot = json.loads((physical / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    require(record["source_snapshot"] == snapshot, "Wrong application physical snapshot")
    expected_inputs = {relative for relative in snapshot["Files"] if relative.startswith("rtl/")} | {"scope_tb.sv"}
    require(set(record["input_hashes"]) == expected_inputs, "Incomplete application input set")
    for relative, expected in record["input_hashes"].items():
        require(digest(directory / relative) == expected, "Scope input changed: " + relative)
        if relative.startswith("rtl/"):
            require(expected == snapshot["Files"][relative] == digest(physical / "source" / relative) == digest(ROOT / relative), "Scope RTL differs from current physical source")
    for key, name in (("capture_sha256", "scope.uart"), ("execute_sha256", "execute.log"), ("compiled_sha256", "scope.vvp")):
        require(digest(directory / name) == record[key], "Scope output changed: " + name)
    terminal = re.findall(r"^PASS scope cycles=(\d+) dumps=2 timeout=1 empty=1$", (directory / "execute.log").read_text(encoding="utf-8"), re.M)
    require(len(terminal) == 1, "Missing unique application terminal result")
    captures = parse_captures((directory / "scope.uart").read_text(encoding="utf-8"), expected_clock_hz=151200000)
    require(len(captures) == 2 and {capture["trigger_mask"] for capture in captures} == {1, 2}, "Both application input channels required")
    for capture in captures:
        require(capture["period_cycles"] == 1210 and capture["late_samples"] == 0, "Scope sampling timebase or lateness changed")
        if capture["trigger_mask"] == 2:
            require(decode_triggered_uart(capture, 9600) == 0x55, "Wrong captured UART waveform")
        else:
            require([level for timestamp, level in transitions(capture, 0)] == [0, 1, 0], "Wrong captured GPIO pulse")
    summaries = [{key: value for key, value in capture.items() if key != "records"} for capture in captures]
    require(record["captures"] == summaries, "Stored capture summary differs from raw UART")
    return {"scope": "source-bound application RTL simulation, not board, CDC or physical timing qualification",
            "simulation_passed": True, "cycles": int(terminal[0]), "captures": summaries,
            "firmware": firmware, "manifest_sha256": digest(directory / "manifest.json"),
            "counter_jumps_used": expected_overrides["timeout_counter_jumps"], "hardware_validated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.directory), indent=2))
