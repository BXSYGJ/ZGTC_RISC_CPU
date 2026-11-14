"""Exercise the actual machine timer and copied 125 MHz CPU MMIO RTL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "build/rtos/timer"
BASE = ROOT / "rtos/baseline125"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iv or not vvp:
        raise RuntimeError("Native Icarus Verilog is required")
    vendor = BASE / "src/cpu/vendor/pacerv_h3"
    if not vendor.is_dir():
        raise FileNotFoundError(vendor)
    rtl = [ROOT / "rtos/rtl/machine_timer.v", ROOT / "rtos/rtl/rv32_cpu_subsys.sv"]
    rtl += sorted(vendor.glob("*.sv"))
    (OUT / "idle.hex").write_text("0000006f\n" + "00000000\n" * 4095, encoding="ascii")
    report = {"passed": False, "sources": {}, "commands": []}
    for path in [HERE / "tb_machine_timer.sv", *rtl]:
        report["sources"][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        for top, token in [("tb_machine_timer", "MACHINE_TIMER_PASS"),
                           ("tb_timer_mmio", "TIMER_MMIO_PASS")]:
            target = OUT / (top + ".vvp")
            commands = [[iv, "-g2012", "-s", top, "-o", str(target),
                         str(HERE / "tb_machine_timer.sv"), *map(str, rtl)],
                        [vvp, "-i", str(target)]]
            for index, command in enumerate(commands):
                proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace", timeout=60)
                output = proc.stdout + proc.stderr
                report["commands"].append({"command": command, "cwd": str(ROOT),
                                            "output": output, "exit_code": proc.returncode})
                (OUT / (top + (".compile.log" if index == 0 else ".log"))).write_text(output, encoding="utf-8")
                if proc.returncode or (index == 1 and token not in output):
                    raise RuntimeError(output)
                if index == 1:
                    print(output, end="")
        report["passed"] = True
    finally:
        (OUT / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RTOS_TIMER_TESTS_PASS cases=2")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
