import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
REPLAY = ROOT.parent / "return_stack_profile"
sys.path.insert(0, str(REPLAY))
from replay import replay, audit_control, file_hash, firmware_image, load_json, require, trace_records


def main():
    control = audit_control()
    require(control["counts"]["interrupt_pending_cycles"] == 0, "Interrupt-containing trace needs explicit stack recovery modeling")
    directory = BASE / "build/execution-profile-current"
    report = load_json(directory / "results.json")
    invocation = load_json(directory / "invocation.json")
    for field, filename in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json"), ("invocation_sha256", "invocation.json"), ("uart_sha256", "uart.log"), ("executable_sha256", "objects/Vrv32_soc")):
        require(file_hash(directory / filename) == report[field], "Retirement evidence changed: " + filename)
    require(report["passed"] is True, "Retirement observer did not pass")
    require(file_hash(directory / "firmware.hex") == invocation["firmware_sha256"], "Retirement firmware changed")
    metadata = load_json(directory / "uart.log.retire.json")
    require(metadata == report["metadata"], "Retirement metadata changed")
    result = replay(trace_records(directory / "uart.log.retire.bin", metadata, firmware_image(directory / "firmware.hex")), depths=(1, 2, 4, 8))
    require(result["counts"]["instructions"] == metadata["records"], "Retirement trace incomplete")
    measured = {entry["pc"]: entry for entry in control["control_pcs"]}
    for entry in result["return_pcs"]:
        entry["observed_mem_events"] = measured.get(entry["pc"], {}).get("mem_events", 0)
        entry["observed_mem_flushes"] = measured.get(entry["pc"], {}).get("mem_flushes", 0)
    result.update(replay_helper_sha256=file_hash(REPLAY / "replay.py"), schema=1, trace_sha256=report["trace_sha256"], profile_report_sha256=file_hash(directory / "results.json"),
                  control_invocation_sha256=control["invocation_sha256"], analyzer_sha256=file_hash(Path(__file__)),
                  hardware_validated=False, measured_cycle_savings=None,
                  hint_reference="RISC-V Unprivileged RV32I: return-address-stack prediction hints, x1/x5 link registers")
    output = ROOT / "build/return-depth-tradeoff.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
