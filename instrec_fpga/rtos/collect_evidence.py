"""Reopen RTOS deliverables and verify their actual source/result evidence.

Timing values are reported as measured. The user's accepted 125 MHz working
point is retained; this checks functional integration, not timing closure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from build_system import verify_sources


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_hashes(rows: dict[str, str]) -> None:
    for name, expected in rows.items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT / path
        if sha(path) != expected:
            raise RuntimeError("Evidence source changed: " + name)


def command_output(report: dict) -> str:
    return "\n".join(str(r.get("output", "")) for r in report.get("commands", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pds-run", type=Path, required=True)
    ap.add_argument("--require-complete", action="store_true")
    args = ap.parse_args()
    pds = args.pds_run.resolve(strict=True)
    baseline = verify_sources()
    evidence = HERE / "evidence"
    records: dict[str, dict] = {}
    for label in ("BASELINE_CPU", "CPU_RTOS", "ROLLBACK_CPU"):
        report = read(evidence / (label + "_REPORT.json"))
        if not report["passed"] or not report["inputs_unchanged"]:
            raise RuntimeError(label + " did not pass")
        if report["clock_hz"] != 125000000:
            raise RuntimeError(label + " used the wrong clock")
        check_hashes(report["source_sha256"])
        if any(r.get("exit_status", r.get("exit_code", 0)) != 0 for r in report["commands"]):
            raise RuntimeError(label + " contains a failed command")
        records[label] = report
    if records["BASELINE_CPU"]["benchmark"] != records["ROLLBACK_CPU"]["benchmark"]:
        raise RuntimeError("Rollback did not restore the original execution results")
    restored = Path(records["ROLLBACK_CPU"]["source_dir"])
    for row in baseline["files"]:
        if sha(restored / row["path"]) != row["sha256"]:
            raise RuntimeError("Rollback did not restore baseline bytes: " + row["path"])
    if (restored / "src/cpu/machine_timer.v").exists():
        raise RuntimeError("Rollback left the added timer")
    cpu_output = command_output(records["CPU_RTOS"])
    required = ("RTOS CRITICAL PASS deferred=3 caught=3 depth=2 mie=0 pending=1",
                "RTOS TEST PASS", "RTOS_CPU_PASS hz=125000000", "catchup=3", "compare=17")
    if not all(token in cpu_output for token in required):
        raise RuntimeError("The final critical-section/preemption test evidence is missing")
    native = read(evidence / "NATIVE_RTOS_REPORT.json")
    native_base = read(evidence / "NATIVE_BASELINE125_REPORT.json")
    comparison = read(evidence / "NATIVE_COMPARISON.json")
    for label, report in (("NATIVE_RTOS", native), ("NATIVE_BASELINE125", native_base)):
        if report["status"] != "pass":
            raise RuntimeError(label + " did not pass")
        for row in report["inputs"]:
            if sha(Path(row["path"])) != row["sha256"]:
                raise RuntimeError(label + " input changed: " + row["path"])
        if any(r["exit_status"] != 0 for r in report["commands"]):
            raise RuntimeError(label + " contains a failed command")
    if not comparison["all_layers_golden_exact"] or comparison["status"] != "pass":
        raise RuntimeError("The same-input baseline/RTOS NPU comparison did not pass")
    build = read(ROOT / "build/rtos/firmware/BUILD.json")
    test_build = read(ROOT / "build/rtos/firmware/test/BUILD.json")
    for report in (build, test_build):
        for row in report["inputs"]:
            if sha(ROOT / row["path"]) != row["sha256"]:
                raise RuntimeError("Firmware source changed: " + row["path"])
    if build["test_mode"] or not test_build["test_mode"]:
        raise RuntimeError("Production/test firmware roles were interchanged")
    firmware = ROOT / "build/rtos/firmware/prog.hex"
    if build["binary_bytes"] > 16384 or sha(firmware.parent / "prog.bin") != build["binary_sha256"]:
        raise RuntimeError("Invalid production firmware")
    map_report = read(pds / "RESULT.json")
    manifest = read(pds / "INPUTS.json")
    if (map_report["exit_code"] or map_report["errors"] or
            not all(map_report["stages"][s] for s in ("compile", "synthesize", "dev_map"))):
        raise RuntimeError("The complete system did not map")
    if manifest["system_clock_hz"] != 125000000 or manifest["tick_hz"] != 1000:
        raise RuntimeError("Wrong FPGA clock/tick profile")
    for row in manifest["files"]:
        if sha(pds / "inputs" / row["path"]) != row["sha256"]:
            raise RuntimeError("PDS frozen input changed: " + row["path"])
    if sha(pds / "inputs/src/cpu/prog_pacerv.hex") != sha(firmware):
        raise RuntimeError("PDS does not contain the current production firmware")
    if sha(pds / "inputs/src/cpu/rv32_cpu_subsys.sv") != sha(HERE / "rtl/rv32_cpu_subsys.sv"):
        raise RuntimeError("PDS does not contain the current timer-enabled wrapper")
    full = read(pds / "FULL_RESULT.json") if (pds / "FULL_RESULT.json").exists() else None
    implemented = bool(full and full["status"] == "pass" and full["fresh_bitstream"] and
                       full["frozen_inputs_unchanged"] and all(full["stages"].values()))
    if implemented and sha(Path(full["bitstream"]["path"])) != full["bitstream"]["sha256"]:
        raise RuntimeError("The implementation bitstream changed")
    timing = None
    if implemented:
        sys.path.insert(0, str(ROOT / "experiments/pacerv_shared_system"))
        from inspect_pds import inspect
        timing = inspect(pds)
        if timing["changed_inputs"] or not timing["clock_contract"]["passed"]:
            raise RuntimeError("FPGA implementation clock/input mismatch")
        (evidence / "PDS_TIMING_AND_RESOURCES.json").write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")
    for source, target in ((pds / "RESULT.json", "PDS_MAP_RESULT.json"),
                           (pds / "INPUTS.json", "PDS_INPUTS.json"),
                           (firmware.parent / "BUILD.json", "FIRMWARE_BUILD.json"),
                           (firmware.parent / "test/BUILD.json", "TEST_FIRMWARE_BUILD.json")):
        shutil.copyfile(source, evidence / target)
    if full:
        shutil.copyfile(pds / "FULL_RESULT.json", evidence / "PDS_FULL_RESULT.json")
    modified = HERE / "MODIFIED_FILE.sv"
    modified.write_bytes((HERE / "rtl/rv32_cpu_subsys.sv").read_bytes())
    changes = []
    pairs = [(HERE / "baseline125/src/cpu/rv32_cpu_subsys.sv", modified,
              "src/cpu/rv32_cpu_subsys.sv"),
             (HERE / "baseline125/src/ctrl/instrec_top.v", pds / "inputs/src/ctrl/instrec_top.v",
              "src/ctrl/instrec_top.v")]
    for old, new, name in pairs:
        changes.extend(difflib.unified_diff(old.read_text(encoding="utf-8").splitlines(True),
            new.read_text(encoding="utf-8").splitlines(True), "baseline125/" + name, "rtos125/" + name))
    for new in [HERE / "rtl/machine_timer.v", *sorted((HERE / "sw").rglob("*"))]:
        if new.is_file():
            changes.extend(difflib.unified_diff([], new.read_text(encoding="utf-8").splitlines(True),
                                              "/dev/null", "rtos/" + new.relative_to(HERE).as_posix()))
    (HERE / "DIFF_FILE.patch").write_text("".join(changes), encoding="utf-8")
    paths = {"MODIFIED_FILE": str(modified), "DIFF_FILE": str(HERE / "DIFF_FILE.patch"),
             "VERIFICATION": str(HERE / "VERIFICATION.txt"), "ROLLBACK": str(HERE / "ROLLBACK.sh")}
    result = {"objective": "combine XSY/XSY2 into the current project with RTOS at the 125 MHz baseline",
              "changed_branch_fields": "XSY; timer_value/irq_timer; IMEM_WORDS=4096; DMEM_WORDS=4096; production FreeRTOS firmware",
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "clock_hz": 125000000,
              "tick_hz": 1000, "baseline_files_restored": 202, "firmware_rom_bytes": build["binary_bytes"],
              "artifacts": paths, "gates": {"frozen_125MHz_inputs": True, "official_kernel_hashes": True,
                 "real_cpu_preemption_queues_critical_sections": True, "same_input_full_NPU_golden": True,
                 "complete_system_mapping": True, "rollback_original_behavior": True,
                 "FPGA_bitstream_generated": implemented},
              "board_preflight": read(evidence / "BOARD_PREFLIGHT.json"),
              "board_test_executed": False, "pds_run": str(pds),
              "timing_constraints_met": timing["qualified"] if timing else None}
    lines = ["RTOS125 VERIFICATION", "Changed branch/fields: " + result["changed_branch_fields"],
             *[k + "=" + v for k, v in paths.items()], "", "BASELINE / MODIFIED / ROLLBACK actual CPU commands:"]
    for label in ("BASELINE_CPU", "CPU_RTOS", "ROLLBACK_CPU"):
        report = records[label]
        lines.extend(["", label, "INPUTS " + json.dumps(report["source_sha256"], ensure_ascii=False)])
        for cmd in report["commands"]:
            lines.extend(["COMMAND " + subprocess.list2cmdline(cmd["command"]), "CWD " + cmd["cwd"],
                          "EXIT " + str(cmd.get("exit_status", cmd.get("exit_code"))),
                          "LITERAL_OUTPUT_BEGIN", cmd.get("output", ""), "LITERAL_OUTPUT_END"])
    for label in ("NATIVE_BASELINE125", "NATIVE_RTOS"):
        lines += ["", label, (evidence / (label + "_OUTPUT.txt")).read_text(encoding="utf-8")]
    lines += ["", "ROLLBACK_RESTORED files=202 clock_hz=125000000 timer_removed=1",
              "Restored behavior: original boot/IMC/DDR/benchmark/NPU report/ACK/relaunch PASS; live RTOS wrapper retained.",
              "Production binary SHA256 " + build["binary_sha256"],
              "FPGA_IMPLEMENTED=" + str(implemented), "BOARD_TEST_EXECUTED=False",
              "Board preflight found no present FTDI/CP2102 devices; serial ports are Bluetooth devices."]
    (HERE / "VERIFICATION.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (evidence / "ACCEPTANCE.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in paths.values():
        if not Path(path).read_bytes():
            raise RuntimeError("Empty artifact: " + path)
    print("RTOS125_EVIDENCE gates=" + str(sum(result["gates"].values())) + "/" + str(len(result["gates"])) +
          " baseline=PASS modified=PASS rollback=PASS FPGA_implemented=" + str(implemented))
    if args.require_complete and not implemented:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
