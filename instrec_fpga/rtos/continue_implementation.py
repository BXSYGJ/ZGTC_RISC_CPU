"""Continue one completed 125 MHz RTOS mapping through PNR and bit generation.

The mapped input manifest and original build recipe remain untouched. A
separate driver project opens the saved PDS project during the execution pass;
using the target project name as the driver would replace its saved state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
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


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def ensure_idle() -> None:
    probe = subprocess.run([
        "pwsh", "-NoProfile", "-Command",
        "if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { exit 2 }"],
        capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if probe.returncode:
        raise RuntimeError("A PDS process is already active")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=90)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.minutes <= 120:
        raise ValueError("minutes must be in 1..120")
    run = args.run_dir.resolve(strict=True)
    if not run.is_relative_to((ROOT / "build/rtos/pds").resolve()):
        raise ValueError("Expected a mapped RTOS build directory")
    manifest_path = run / "INPUTS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mapped_path = run / "RESULT.json"
    mapped = json.loads(mapped_path.read_text(encoding="utf-8"))
    if (mapped["exit_code"] != 0 or mapped["errors"] or
            not mapped["frozen_inputs_unchanged"] or
            not all(mapped["stages"][name] for name in ("compile", "synthesize", "dev_map"))):
        raise RuntimeError("The source map flow did not finish successfully")
    if manifest["system_clock_hz"] != 125000000 or manifest["tick_hz"] != 1000:
        raise RuntimeError("Expected the actual 125 MHz / 1 kHz RTOS profile")

    def verify_inputs() -> None:
        for row in manifest["files"]:
            if sha(run / "inputs" / row["path"]) != row["sha256"]:
                raise RuntimeError("Frozen input changed: " + row["path"])

    verify_inputs()
    project = run / "instrec_rtos_125.pds"
    database = run / "device_map/instrec_top_map.adf"
    if not database.is_file() or "PG2L100H" not in project.read_text(encoding="utf-8"):
        raise RuntimeError("Missing mapped PG2L100H database or project")
    pnr_lines = [line for line in (HERE / "baseline125/SOURCE_BUILD_RECIPE.tcl").read_text(
        encoding="utf-8").splitlines() if line.startswith("pnr ")]
    if len(pnr_lines) != 1 or "-gplace_seed 2 " not in pnr_lines[0] or "-fix_hold_violation_iterations 8" not in pnr_lines[0]:
        raise RuntimeError("Unexpected selected 125 MHz PNR configuration")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    attempt = run / "continuations" / stamp
    attempt.mkdir(parents=True, exist_ok=False)
    backup = attempt / "backup"
    backup.mkdir()
    for source in (project, database, manifest_path, run / "build.tcl", mapped_path):
        shutil.copyfile(source, backup / source.name)
    before = {p.relative_to(run).as_posix(): sha(p) for directory in ("compile", "synthesize", "device_map")
              for p in sorted((run / directory).rglob("*")) if p.is_file()}
    controls = {p.name: sha(p) for p in (manifest_path, run / "build.tcl", mapped_path)}
    driver = "rtos_continue_" + stamp.replace("-", "_")
    # PDS evaluates the script twice. open_project exists only in the real
    # execution pass. The distinct -project_name is essential: -file creates
    # its driver project before this script can reopen the mapped project.
    script = attempt / "continue.tcl"
    lines = ["if {[llength [info commands open_project]]} {",
             "    open_project {" + project.as_posix() + "}",
             "    puts {RTOS_MAPPED_PROJECT_OPENED}", "}",
             pnr_lines[0], "report_timing", "gen_bit_stream",
             "if {[llength [info commands open_project]]} {exit}"]
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = {"status": "prepared", "attempt": str(attempt), "source_map_result_sha256": sha(mapped_path),
             "manifest_sha256": sha(manifest_path), "database_sha256_before": sha(database),
             "project_sha256_before": sha(project), "pnr_command": pnr_lines[0],
             "driver_project": driver, "script_sha256": sha(script),
             "source_control_hashes": controls, "prior_database_hashes": before,
             "input_count": len(manifest["files"]), "target": manifest["target"],
             "system_clock_hz": manifest["system_clock_hz"], "max_minutes": args.minutes}
    save(attempt / "FULL_RESULT.json", state)
    print("RTOS_CONTINUATION_PREPARED " + str(attempt), flush=True)
    if args.prepare_only:
        return 0
    ensure_idle()
    pds = Path(os.environ.get("PDS_ROOT", "D:/PDS_2022.2-SP6.4")) / "bin/pds_shell.exe"
    if not pds.is_file():
        raise FileNotFoundError(pds)
    stdout_path, stderr_path = attempt / "pds.stdout.log", attempt / "pds.stderr.log"
    command = [str(pds), "-file", str(script), "-work_dir", str(run), "-project_name", driver]
    start_wall = time.time()
    start = time.monotonic()
    ensure_idle()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.Popen(command, cwd=run, stdout=stdout, stderr=stderr,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        state.update(status="running", pid=process.pid, command=command,
                     stdout_path=str(stdout_path), stderr_path=str(stderr_path))
        save(attempt / "FULL_RESULT.json", state)
        save(run / "FULL_PROCESS.json", state)
        print("RTOS_CONTINUATION_PID " + str(process.pid), flush=True)
        timed_out = False
        try:
            code = process.wait(timeout=args.minutes * 60)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=30)
    output = stdout_path.read_text(encoding="utf-8", errors="replace")
    output += stderr_path.read_text(encoding="utf-8", errors="replace")
    stages = {name: bool(re.search(r"Executing\s*:\s*" + name + r"\b[^\r\n]*successfully\.", output))
              for name in ("pnr", "report_timing", "gen_bit_stream")}
    errors = [line for line in output.splitlines() if line.startswith("E:") and
              "SCBV has not been set" not in line and "Bitstream-2001" not in line]
    verify_inputs()
    controls_unchanged = all(sha(run / name) == digest for name, digest in controls.items())
    mapping_unchanged = sha(database) == state["database_sha256_before"]
    expected_project = "PG2L100H" in project.read_text(encoding="utf-8", errors="replace")
    bit = run / "generate_bitstream/instrec_top.sbit"
    fresh_bit = bit.is_file() and bit.stat().st_mtime >= start_wall - 1
    good = (code == 0 and not timed_out and not errors and all(stages.values()) and
            controls_unchanged and mapping_unchanged and expected_project and fresh_bit)
    state.update(status="pass" if good else "failed", exit_code=code, timed_out=timed_out,
                 seconds=round(time.monotonic()-start, 3), stages=stages, errors=errors,
                 source_controls_unchanged=controls_unchanged, frozen_inputs_unchanged=True,
                 mapped_database_reused_unchanged=mapping_unchanged,
                 project_target_preserved=expected_project, fresh_bitstream=fresh_bit)
    if fresh_bit:
        state["bitstream"] = {"path": str(bit), "bytes": bit.stat().st_size, "sha256": sha(bit)}
    timing = run / "report_timing/instrec_top.rtr"
    if timing.is_file():
        state["timing_report"] = {"path": str(timing), "sha256": sha(timing)}
    if not expected_project:
        shutil.copyfile(backup / project.name, project)
        state["project_restored_from_backup"] = True
    save(attempt / "FULL_RESULT.json", state)
    save(run / "FULL_RESULT.json", state)
    print("RTOS_CONTINUATION_" + ("PASS" if good else "FAILED") + " " + str(attempt / "FULL_RESULT.json"), flush=True)
    return 0 if good else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
