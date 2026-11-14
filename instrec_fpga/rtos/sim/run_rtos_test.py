"""Run the real FreeRTOS firmware on the 125 MHz PaceRV RTL integration.

The NPU and DDR in this test are transaction-level peripheral models. Kernel,
tasks, context switches, timer, local memories and MMIO all execute as RTL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rom_banks import validate_banks

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--firmware", type=Path,
                    default=ROOT / "build/rtos/firmware/test/prog.hex")
    ap.add_argument("--firmware-even", type=Path,
                    help="Even ROM bank; defaults to <firmware stem>_even.hex")
    ap.add_argument("--firmware-odd", type=Path,
                    help="Odd ROM bank; defaults to <firmware stem>_odd.hex")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--label", default="cpu")
    ap.add_argument("--backend", choices=("iverilog", "verilator-wsl"), default="verilator-wsl")
    ap.add_argument("--progress", action="store_true")
    args = ap.parse_args()
    firmware = args.firmware.resolve(strict=True)
    even = (args.firmware_even or firmware.with_name(firmware.stem + "_even" + firmware.suffix)).resolve(strict=True)
    odd = (args.firmware_odd or firmware.with_name(firmware.stem + "_odd" + firmware.suffix)).resolve(strict=True)
    validate_banks(firmware, even, odd, 4096)
    if not args.label.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Label must be alphanumeric with optional hyphens/underscores")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out = ROOT / "build/rtos/sim" / (args.label + "-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    iv = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if args.backend == "iverilog" and (not iv or not vvp):
        raise RuntimeError("Native iverilog and vvp are required")
    frozen = ROOT / "rtos/baseline125"
    vendor = frozen / "src/cpu/vendor/pacerv_h3"
    if not vendor.is_dir():
        raise FileNotFoundError("The selected 125 MHz frozen inputs are required: " + str(vendor))
    rtl = [ROOT / "rtos/rtl/rv32_cpu_subsys.sv", ROOT / "rtos/rtl/machine_timer.v"]
    rtl += sorted(vendor.glob("*.sv"))
    if len(rtl) != 10:
        raise RuntimeError("Expected 8 frozen PaceRV sources and 2 integration sources")
    source_files = [HERE / "tb_rtos_cpu.sv", HERE / "rom_banks.py", firmware, even, odd, *rtl]
    frozen_files = []
    for path in source_files:
        target = out / "inputs" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        frozen_files.append(target)
    bench, helper, frozen_firmware, frozen_even, frozen_odd, *frozen_rtl = frozen_files
    validate_banks(frozen_firmware, frozen_even, frozen_odd, 4096)
    files = frozen_files
    report = {
        "scope": "real FreeRTOS tasks on frozen 125 MHz PaceRV RTL; modeled NPU/DDR peripherals",
        "clock_hz": 125000000,
        "backend": args.backend,
        "rom_words": 4096, "rom_banks_verified": True,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in source_files},
        "input_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
        "commands": [], "passed": False,
    }

    def run(command: list[str], timeout: int) -> dict:
        begin = time.monotonic()
        log = out / ("command-" + str(len(report["commands"])) + ".log")
        error_log = out / ("command-" + str(len(report["commands"])) + ".stderr.log")
        def decode(path: Path) -> str:
            data = path.read_bytes()
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                return data.decode("utf-16", "replace")
            if data.count(b"\x00") > len(data) // 8:
                return data.decode("utf-16-le", "replace")
            return data.decode("utf-8", "replace")
        try:
            with log.open("wb") as output, error_log.open("wb") as errors:
                proc = subprocess.run(command, cwd=ROOT, stdout=output,
                                      stderr=errors, timeout=timeout)
            record = {"command": command, "cwd": str(ROOT),
                      "exit_status": proc.returncode,
                      "output": decode(log) + decode(error_log),
                      "elapsed_seconds": round(time.monotonic() - begin, 3)}
        except subprocess.TimeoutExpired as exc:
            record = {"command": command, "cwd": str(ROOT), "exit_status": "timeout",
                      "output": decode(log) + decode(error_log),
                      "elapsed_seconds": round(time.monotonic() - begin, 3)}
        report["commands"].append(record)
        return record

    try:
        binary = out / "tb_rtos_cpu.vvp"
        if args.backend == "iverilog":
            command = [iv, "-g2012", "-s", "tb_rtos_cpu", "-o", str(binary),
                       '-DRTOS_PROG_HEX="' + frozen_firmware.as_posix() + '"',
                       '-DRTOS_PROG_EVEN_HEX="' + frozen_even.as_posix() + '"',
                       '-DRTOS_PROG_ODD_HEX="' + frozen_odd.as_posix() + '"',
                       str(bench), *map(str, frozen_rtl)]
            execute = [vvp, "-i", str(binary)]
        else:
            def linux_path(path: Path) -> str:
                p = path.resolve().as_posix()
                if len(p) < 3 or p[1:3] != ":/":
                    raise ValueError("Expected a Windows absolute path: " + p)
                return "/mnt/" + p[0].lower() + p[2:]
            # The firmware address in generated HDL must use the path visible
            # to the actual simulator process, which runs directly under WSL.
            text = bench.read_text(encoding="ascii")
            for name, path in (("prog.hex", frozen_firmware), ("prog_even.hex", frozen_even),
                               ("prog_odd.hex", frozen_odd)):
                default = '"build/rtos/firmware/test/' + name + '"'
                if text.count(default) != 1:
                    raise RuntimeError("Expected a unique testbench ROM default: " + default)
                text = text.replace(default, '"' + linux_path(path) + '"')
            bench.write_text(text, encoding="ascii")
            report["input_sha256"][str(bench.relative_to(ROOT))] = digest(bench)
            prefix = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", linux_path(ROOT), "--exec"]
            binary = out / "obj/Vtb_rtos_cpu"
            command = prefix + ["/home/bx/.local/src/verilator-5.040/bin/verilator",
                                "--binary", "--timing", "-Wno-fatal", "-j", "2",
                                "--top-module", "tb_rtos_cpu", "--Mdir", linux_path(binary.parent),
                                "-CFLAGS", "-O2", linux_path(bench), *map(linux_path, frozen_rtl)]
            execute = prefix + [linux_path(binary)]
        result = run(command, 1200)
        if result["exit_status"] != 0:
            raise RuntimeError(result["output"])
        print("RTOS_CPU_SIM_STARTED out=" + str(out), flush=True)
        result = run(execute + (["+rtos_progress"] if args.progress else []), args.timeout)
        print(result["output"], end="", flush=True)
        (out / "UART_AND_RTL.log").write_text(result["output"], encoding="utf-8")
        required = ["RTOS_ROM_BANKS_PASS words=4096 instruction_banks=2 data_image=1",
                    "RTOS_CPU_PASS", "RTOS BOOT hz=125000000 tick=1000",
                    "RTOS NPU top1=5 last_class=3 last_p=87 c=12345",
                    "RTOS NPU TIMEOUT", "RTOS NPU top1=2 last_class=6 last_p=64 c=54321",
                    "RTOS CRITICAL PASS", "RTOS TEST PASS"]
        report["required_output"] = {token: token in result["output"] for token in required}
        report["inputs_unchanged"] = all(digest(p) == report["input_sha256"][str(p.relative_to(ROOT))]
                                          for p in files)
        report["passed"] = (result["exit_status"] == 0 and
                            all(report["required_output"].values()) and report["inputs_unchanged"])
        if not report["passed"]:
            raise RuntimeError("RTOS CPU validation failed; see " + str(out / "RESULT.json"))
    finally:
        (out / "RESULT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
        lines = ["RTOS125 CPU VERIFICATION", "Input hashes:",
                 *[key + " " + val for key, val in report["input_sha256"].items()]]
        for record in report["commands"]:
            lines += ["", "COMMAND " + subprocess.list2cmdline(record["command"]),
                      "CWD " + record["cwd"], "EXIT " + str(record["exit_status"]),
                      "LITERAL_OUTPUT_BEGIN", record["output"], "LITERAL_OUTPUT_END"]
        lines += ["", "PASSED=" + str(report["passed"])]
        (out / "VERIFICATION.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("RTOS_CPU_EVIDENCE " + str(out / "RESULT.json"), flush=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
