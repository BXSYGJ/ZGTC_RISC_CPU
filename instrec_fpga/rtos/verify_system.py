"""Rebuild, execute and archive all functional checks for a 125 MHz RTOS build.

Run this after build_system.py has mapped or implemented a project. Every test
uses this checkout. Historical absolute paths and ignored build directories
from an earlier machine are not prerequisites. PDS is never launched here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assert_commands(report: dict, status: str) -> None:
    if report.get("status", "pass" if report.get("passed") else "failed") != status:
        raise RuntimeError("A functional test did not pass")
    if not report.get("commands") or any(
            row.get("exit_status", row.get("exit_code")) != 0 for row in report["commands"]):
        raise RuntimeError("A functional test contains a failed command")


def native_comparison(before_path: Path, after_path: Path) -> dict:
    """Derive a comparison from current successful runs and their real inputs.

    This function has no write side effects, so existing reports can also be
    audited without replacing evidence or starting another simulation.
    """
    before, after = read(before_path), read(after_path)
    if before["firmware"] != "baseline125" or after["firmware"] != "rtos":
        raise RuntimeError("Native baseline/RTOS reports were interchanged")
    maps = []
    for report in (before, after):
        assert_commands(report, "pass")
        if not report["frame_major"]:
            raise RuntimeError("Native inference did not use the production feature layout")
        rows = {}
        for row in report["inputs"]:
            path = Path(row["path"])
            if sha(path) != row["sha256"]:
                raise RuntimeError("Native run input changed: " + str(path))
            rows[path.resolve()] = row["sha256"]
        maps.append(rows)
    if before["weight_image_sha256"] != after["weight_image_sha256"]:
        raise RuntimeError("The before/after weight images differ")

    baseline_root = HERE / "baseline125"
    manifest = read(HERE / "BASELINE.json")
    npu = {r["path"]: r["sha256"] for r in manifest["files"]
           if r["path"].startswith("src/npu/") and r["path"].endswith(".v")}
    if len(npu) != 15:
        raise RuntimeError("Expected the complete 15-file frozen NPU")
    for name, expected in npu.items():
        path = (baseline_root / name).resolve()
        if any(rows.get(path) != expected for rows in maps):
            raise RuntimeError("The native runs did not execute the same frozen NPU: " + name)

    required_assets = {"weights.hex", "feat.hex", "gap.hex", "fc1.hex",
                       "fc2_logits.hex", "probs.hex"}
    required_assets |= {kind + str(i) + ".hex" for kind in ("conv", "pool") for i in range(1, 5)}
    assets = [{p.name: (p, digest) for p, digest in rows.items()
               if p.parent.name == "assets" and p.name in required_assets} for rows in maps]
    if any(set(group) != required_assets for group in assets):
        raise RuntimeError("The native runs do not contain all 14 feature/weight/golden assets")
    same_assets = {}
    for name in sorted(required_assets):
        if assets[0][name][1] != assets[1][name][1]:
            raise RuntimeError("The native before/after assets differ: " + name)
        same_assets[name] = assets[0][name][1]

    outputs = [report["commands"][-1]["output"] for report in (before, after)]
    payloads, controllers, transactions = [], [], []
    for index, output in enumerate(outputs):
        controller = re.search(r"RESULT: PASS full native controller npu_top golden inference cycles=(\d+)", output)
        complete = ("RESULT: PASS production FreeRTOS tasks, full native golden NPU, immutable queue result report and acknowledgement"
                    if index else "RESULT: PASS real CPU ROM MMIO launch, full native golden NPU, real result report and acknowledgement")
        if not controller or complete not in output:
            raise RuntimeError("A complete native golden inference result is missing")
        if "RESULT: PASS four convs and DDR activation replay golden exact" not in output:
            raise RuntimeError("The native convolution/replay comparison is missing")
        payload = re.findall(r"CPU UART (?:RTOS )?NPU top1=(\d+) last_class=(\d+) last_p=(\d+) c=(\d+)(?: seq=(\d+) tick=(\d+))?", output)
        if len(payload) != 1:
            raise RuntimeError("Expected exactly one actual UART inference result")
        payloads.append(tuple(map(int, payload[0][:4])))
        controllers.append(int(controller[1]))
        transaction = re.search(r"(?:RTOS|BASELINE)_NATIVE DDR requests=(\d+) responses=(\d+)", output)
        if not transaction or int(transaction[1]) != int(transaction[2]) or int(transaction[1]) == 0:
            raise RuntimeError("The native DDR transactions did not complete")
        transactions.append(tuple(map(int, transaction.groups())))
    if payloads[0] != payloads[1] or controllers[0] != controllers[1]:
        raise RuntimeError("The actual native result/cycle counts changed after RTOS integration")
    scheduling = re.search(r"RTOS_NATIVE scheduling timer_irqs=(\d+) yield_traps=(\d+) heartbeats_while_busy=(\d+)", outputs[1])
    if not scheduling or any(int(value) < minimum for value, minimum in zip(scheduling.groups(), (100, 100, 2))):
        raise RuntimeError("The production RTOS did not remain scheduled during full inference")
    actual = after.get("actual_result")
    if not actual or tuple(actual[:4]) != payloads[1] or actual[4] != 1:
        raise RuntimeError("The RTOS result record differs from its actual UART output")
    counts = {Path(name).stem: sum(1 for _ in assets[1][name][0].open(encoding="ascii"))
              for name in required_assets - {"feat.hex", "weights.hex"}}
    return {
        "status": "pass", "clock_hz": 125000000,
        "production_RV32_ROM_bytes": read(ROOT / "build/rtos/firmware/BUILD.json")["binary_bytes"],
        "before": {"mode": "original 125 MHz wrapper and firmware", "report": str(before_path),
                   "command": before["commands"][-1]["command"], "cwd": before["commands"][-1]["cwd"],
                   "exit_status": 0, "DDR_requests": transactions[0][0], "DDR_responses": transactions[0][1],
                   "controller_cycles": controllers[0], "firmware_captured_cycles": payloads[0][3]},
        "after": {"mode": "production FreeRTOS firmware and machine-timer wrapper", "report": str(after_path),
                  "command": after["commands"][-1]["command"], "cwd": after["commands"][-1]["cwd"],
                  "exit_status": 0, "DDR_requests": transactions[1][0], "DDR_responses": transactions[1][1],
                  "controller_cycles": controllers[1], "firmware_captured_cycles": payloads[1][3],
                  "tick_interrupts": int(scheduling[1]), "yield_traps": int(scheduling[2]),
                  "heartbeats_during_NPU_busy": int(scheduling[3]),
                  "result_sequence": actual[4], "result_tick": actual[5]},
        "golden_output_counts": counts,
        "all_layers_golden_exact": True,
        "same_NPU_sources": npu, "same_assets_sha256": same_assets,
        "limitations": "Actual frozen NPU/CPU/DDR RTL and production RTOS ROM execute with preloaded feature/weight assets and a behavioral DDR physical model. Audio/Mel acquisition, HDMI pins and physical board behavior have separate validation.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pds-run", type=Path, required=True)
    parser.add_argument("--require-complete", action="store_true",
                        help="Also require the existing PDS run to contain a completed bitstream")
    args = parser.parse_args()
    pds = args.pds_run.resolve(strict=True)
    manifest = read(pds / "INPUTS.json")
    mapped = read(pds / "RESULT.json")
    if (mapped["exit_code"] != 0 or mapped["errors"] or not mapped["frozen_inputs_unchanged"] or
            not all(mapped["stages"][name] for name in ("compile", "synthesize", "dev_map"))):
        raise RuntimeError("The supplied RTOS project has not completed mapping successfully")
    if manifest["system_clock_hz"] != 125000000 or manifest["tick_hz"] != 1000:
        raise RuntimeError("Expected a mapped 125 MHz / 1 kHz RTOS project")
    if manifest["rom_bytes"] != 16384 or manifest["ram_bytes"] != 16384:
        raise RuntimeError("Expected the common 16 KiB ROM / 16 KiB RAM profile")
    sys.path.insert(0, str(HERE))
    from audit_mapped_rom import verify_report as verify_mapped_rom
    verify_mapped_rom(pds)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    study = ROOT / "build/rtos/verify" / stamp
    study.mkdir(parents=True, exist_ok=False)
    evidence = HERE / "evidence"
    if evidence.is_dir():
        shutil.copytree(evidence, study / "previous_evidence")
    else:
        evidence.mkdir()
    orchestration = {"status": "running", "pds_run": str(pds), "study": str(study), "commands": []}

    def execute(name: str, command: list[str], timeout: int = 1800) -> dict:
        number = len(orchestration["commands"])
        log = study / (f"{number:02d}_" + name + ".stdout.log")
        errors = study / (f"{number:02d}_" + name + ".stderr.log")
        print("RTOS_VERIFY " + name, flush=True)
        started = time.monotonic()
        with log.open("wb") as stdout, errors.open("wb") as stderr:
            try:
                proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        def decode(path: Path) -> str:
            raw = path.read_bytes()
            encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else (
                "utf-16-le" if raw.count(b"\x00") > len(raw) // 8 else "utf-8")
            return raw.decode(encoding, "replace")
        row = {"command": command, "cwd": str(ROOT), "exit_status": code,
               "seconds": round(time.monotonic() - started, 3), "output": decode(log) + decode(errors)}
        orchestration["commands"].append(row)
        write(study / "RESULT.json", orchestration)
        if code != 0:
            raise RuntimeError(name + " failed; literal output is in " + str(log))
        return row

    def python(name: str, relative: str, *arguments: str) -> dict:
        return execute(name, [sys.executable, "-X", "utf8", str(HERE / relative), *arguments])

    def cpu_archive(label: str, command: dict, token: str) -> dict:
        found = re.findall(re.escape(token) + r" (.+)", command["output"])
        if len(found) != 1:
            raise RuntimeError("Missing unique CPU report path in actual output: " + label)
        report_path = Path(found[0].strip())
        report = read(report_path)
        assert_commands(report, "pass")
        if not report["inputs_unchanged"] or report["clock_hz"] != 125000000:
            raise RuntimeError("CPU inputs/clock did not match: " + label)
        shutil.copyfile(report_path, evidence / (label + "_REPORT.json"))
        shutil.copyfile(report_path.parent / "VERIFICATION.txt", evidence / (label + "_VERIFICATION.txt"))
        (evidence / (label + "_OUTPUT.txt")).write_text(report["commands"][-1]["output"], encoding="utf-8")
        return report

    try:
        python("firmware", "build_firmware.py")
        python("test_firmware", "build_firmware.py", "--test")
        firmware = ROOT / "build/rtos/firmware/prog.hex"
        for name, source in (("prog_pacerv.hex", firmware),
                             ("prog_pacerv_even.hex", firmware.with_name("prog_even.hex")),
                             ("prog_pacerv_odd.hex", firmware.with_name("prog_odd.hex")),
                             ("rv32_cpu_subsys.sv", HERE / "rtl/rv32_cpu_subsys.sv"),
                             ("machine_timer.v", HERE / "rtl/machine_timer.v")):
            if sha(pds / "inputs/src/cpu" / name) != sha(source):
                raise RuntimeError("The supplied PDS project differs from this checkout; rebuild it: " + name)
        for row in manifest["files"]:
            if sha(pds / "inputs" / row["path"]) != row["sha256"]:
                raise RuntimeError("PDS frozen input changed: " + row["path"])
        for name, relative, result in (("timer", "sim/run_timer_test.py", "timer/RESULTS.json"),
                                       ("irq", "sim/run_irq_precision.py", "irq_precision/RESULTS.json"),
                                       ("rom_readout", "sim/run_rom_readout.py", "rom_readout/RESULTS.json")):
            python(name, relative)
            path = ROOT / "build/rtos" / result
            value = read(path)
            assert_commands(value, "pass")
            if not value["inputs_unchanged"]:
                raise RuntimeError("Peripheral test inputs changed: " + name)
            shutil.copyfile(path, evidence / (name.upper() + "_REPORT.json"))
        original = cpu_archive("BASELINE_CPU", python("baseline_cpu", "sim/run_baseline.py", "--label", "verifybase_" + stamp), "BASELINE125_EVIDENCE")
        cpu_archive("CPU_RTOS", python("rtos_cpu", "sim/run_rtos_test.py", "--label", "verifyrtos_" + stamp), "RTOS_CPU_EVIDENCE")
        rollback = study / "rollback_copy"
        shutil.copytree(pds / "inputs", rollback)
        execute("rollback", ["pwsh", "-NoProfile", "-File", str(HERE / "ROLLBACK.ps1"), "-Workspace", str(rollback)])
        restored = read(HERE / "BASELINE.json")
        removed = ("machine_timer.v", "prog_pacerv_even.hex", "prog_pacerv_odd.hex")
        if (any(sha(rollback / row["path"]) != row["sha256"] for row in restored["files"]) or
                any((rollback / "src/cpu" / name).exists() for name in removed)):
            raise RuntimeError("Rollback did not restore the 202 baseline files")
        rolled = cpu_archive("ROLLBACK_CPU", python("rollback_cpu", "sim/run_baseline.py", "--source-dir", str(rollback), "--label", "verifyrollback_" + stamp), "BASELINE125_EVIDENCE")
        if original["benchmark"] != rolled["benchmark"]:
            raise RuntimeError("Rollback execution differs from the baseline")

        reports = []
        for mode, label in (("baseline125", "NATIVE_BASELINE125"), ("rtos", "NATIVE_RTOS")):
            run_label = "verify_" + stamp
            python("native_" + mode, "sim/run_native_rtos.py", "--firmware", mode, "--run-label", run_label)
            report = ROOT / "build/sim" / ("cpu_native_joint_" + ("rtos125_" if mode == "rtos" else "baseline125_") + run_label) / "PACERV_NATIVE_REPORT.json"
            reports.append(report)
            value = read(report)
            assert_commands(value, "pass")
            shutil.copyfile(report, evidence / (label + "_REPORT.json"))
            (evidence / (label + "_OUTPUT.txt")).write_text(value["commands"][-1]["output"], encoding="utf-8")
        comparison = native_comparison(*reports)
        comparison["archives"] = {name: {"sha256": sha(evidence / name), "bytes": (evidence / name).stat().st_size}
                                  for name in ("NATIVE_BASELINE125_REPORT.json", "NATIVE_BASELINE125_OUTPUT.txt",
                                               "NATIVE_RTOS_REPORT.json", "NATIVE_RTOS_OUTPUT.txt")}
        write(evidence / "NATIVE_COMPARISON.json", comparison)
        python("collect", "collect_evidence.py", "--pds-run", str(pds),
               *(["--require-complete"] if args.require_complete else []))
        orchestration["status"] = "pass"
        print("RTOS_VERIFY_PASS " + str(study / "RESULT.json"), flush=True)
        return 0
    except BaseException as exc:
        orchestration.update(status="failed", error=repr(exc))
        raise
    finally:
        write(study / "RESULT.json", orchestration)
        shutil.copyfile(study / "RESULT.json", evidence / "FUNCTIONAL_VERIFICATION.json")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
