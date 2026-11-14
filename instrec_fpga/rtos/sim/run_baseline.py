"""Execute the selected 125 MHz firmware/core, including a restored copy.

The --source-dir directory must contain the frozen src/cpu layout. The
transaction-level NPU and DDR stimuli match run_rtos_test.py where applicable.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from output_decode import decode_mixed_output

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux_path(path: Path) -> str:
    p = path.resolve().as_posix()
    if len(p) < 3 or p[1:3] != ":/":
        raise ValueError("Expected a Windows absolute path: " + p)
    return "/mnt/" + p[0].lower() + p[2:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", type=Path, default=ROOT / "rtos/baseline125")
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--backend", choices=("verilator-wsl", "iverilog"), default="verilator-wsl")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    if not args.label.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Invalid label")
    source = args.source_dir.resolve(strict=True)
    out = ROOT / "build/rtos/sim" / (args.label + "-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    out.mkdir(parents=True, exist_ok=False)
    originals = [source / "src/cpu/prog_pacerv.hex", source / "src/cpu/rv32_cpu_subsys.sv"]
    originals += sorted((source / "src/cpu/vendor/pacerv_h3").glob("*.sv"))
    if len(originals) != 10 or not all(p.is_file() for p in originals):
        raise RuntimeError("Expected the selected firmware, wrapper and eight vendor RTL files")
    copies = []
    for path in originals:
        target = out / "inputs" / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copies.append(target)
    firmware, *rtl = copies
    bench = out / "inputs/tb_baseline125.sv"
    text = (HERE / "tb_baseline125.sv").read_text(encoding="ascii")
    firmware_path = linux_path(firmware) if args.backend == "verilator-wsl" else firmware.as_posix()
    text = text.replace('"rtos/baseline125/src/cpu/prog_pacerv.hex"', '"' + firmware_path + '"')
    bench.write_text(text, encoding="ascii")
    copies.append(bench)
    decoder = HERE / "output_decode.py"
    frozen_decoder = out / "inputs/output_decode.py"
    shutil.copy2(decoder, frozen_decoder)
    copies.append(frozen_decoder)
    report = {"scope": "original selected 125 MHz firmware on the frozen PaceRV RTL, modeled NPU/DDR",
              "source_dir": str(source), "clock_hz": 125000000, "backend": args.backend,
              "source_sha256": {str(p): sha(p) for p in [*originals, decoder]},
              "frozen_sha256": {str(p.relative_to(out)): sha(p) for p in copies},
              "commands": [], "passed": False}

    def run(command: list[str], timeout: int) -> dict:
        start = time.monotonic()
        log = out / ("command-" + str(len(report["commands"])) + ".log")
        error_log = out / ("command-" + str(len(report["commands"])) + ".stderr.log")
        with log.open("wb") as stream, error_log.open("wb") as errors:
            try:
                proc = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=errors,
                                      timeout=timeout)
                status = proc.returncode
            except subprocess.TimeoutExpired:
                status = "timeout"
        output = decode_mixed_output(log.read_bytes()) + decode_mixed_output(error_log.read_bytes())
        row = {"command": command, "cwd": str(ROOT), "exit_status": status,
               "elapsed_seconds": round(time.monotonic() - start, 3), "output": output}
        report["commands"].append(row)
        return row

    try:
        if args.backend == "verilator-wsl":
            prefix = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", linux_path(ROOT), "--exec"]
            binary = out / "obj/Vtb_baseline125"
            command = prefix + ["/home/bx/.local/src/verilator-5.040/bin/verilator", "--binary",
                                "--timing", "-Wno-fatal", "-j", "2", "--top-module", "tb_baseline125",
                                "--Mdir", linux_path(binary.parent), "-CFLAGS", "-O2",
                                linux_path(bench), *map(linux_path, rtl)]
            execute = prefix + [linux_path(binary)]
        else:
            iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
            if not iv or not vvp: raise RuntimeError("Native Icarus is required")
            binary = out / "tb_baseline125.vvp"
            command = [iv, "-g2012", "-s", "tb_baseline125", "-o", str(binary), str(bench), *map(str, rtl)]
            execute = [vvp, "-i", str(binary)]
        print("BASELINE125_COMPILING out=" + str(out), flush=True)
        result = run(command, 1200)
        if result["exit_status"] != 0: raise RuntimeError(result["output"])
        print("BASELINE125_RUNNING out=" + str(out), flush=True)
        result = run(execute, args.timeout)
        print(result["output"], end="", flush=True)
        benchmark = re.search(r"RV32 BENCH cycles=(\d+) inst=(\d+) acc=(0x[0-9a-f]+)", result["output"])
        if benchmark:
            report["benchmark"] = {"cycles": int(benchmark[1]), "instructions": int(benchmark[2]),
                                   "accumulator": benchmark[3]}
        report["inputs_unchanged"] = all(sha(p) == report["frozen_sha256"][str(p.relative_to(out))] for p in copies)
        report["passed"] = result["exit_status"] == 0 and "BASELINE125_CPU_PASS" in result["output"] and report["inputs_unchanged"]
        if not report["passed"]: raise RuntimeError("125 MHz baseline did not pass; see " + str(out))
    finally:
        (out / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lines = ["BASELINE125 VERIFICATION", "SOURCE " + str(source), "INPUT_SHA256"]
        lines += [name + " " + value for name, value in report["frozen_sha256"].items()]
        for row in report["commands"]:
            lines += ["", "COMMAND " + subprocess.list2cmdline(row["command"]), "CWD " + row["cwd"],
                      "EXIT " + str(row["exit_status"]), "LITERAL_OUTPUT_BEGIN", row["output"], "LITERAL_OUTPUT_END"]
        lines += ["", "PASSED=" + str(report["passed"])]
        (out / "VERIFICATION.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("BASELINE125_EVIDENCE " + str(out / "RESULT.json"), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
