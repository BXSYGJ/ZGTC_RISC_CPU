"""Exercise the actual machine timer and copied 125 MHz CPU MMIO RTL."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from rom_banks import split_rom

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
    image = OUT / "idle.hex"
    image.write_text("0000006f\n" + "00000000\n" * 4095, encoding="ascii")
    images = [image, *split_rom(image, 4096)]
    sources = [HERE / "tb_machine_timer.sv", HERE / "rom_banks.py", *images, *rtl]
    frozen = []
    for path in sources:
        target = OUT / "inputs" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        frozen.append(target)
    bench, helper, prog, even, odd, *frozen_rtl = frozen
    report = {"passed": False, "sources": {}, "input_sha256": {}, "commands": []}
    for field, paths in (("sources", sources), ("input_sha256", frozen)):
        report[field] = {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in paths}
    try:
        for top, token in [("tb_machine_timer", "MACHINE_TIMER_PASS"),
                           ("tb_timer_mmio", "TIMER_MMIO_PASS")]:
            target = OUT / (top + ".vvp")
            commands = [[iv, "-g2012", "-s", top, "-o", str(target),
                         '-DTIMER_PROG_HEX="' + prog.as_posix() + '"',
                         '-DTIMER_PROG_EVEN_HEX="' + even.as_posix() + '"',
                         '-DTIMER_PROG_ODD_HEX="' + odd.as_posix() + '"',
                         str(bench), *map(str, frozen_rtl)],
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
        report["inputs_unchanged"] = all(
            hashlib.sha256(path.read_bytes()).hexdigest() == report["input_sha256"][path.relative_to(ROOT).as_posix()]
            for path in frozen)
        if not report["inputs_unchanged"]:
            raise RuntimeError("The frozen timer inputs changed during simulation")
        report["passed"] = True
    finally:
        (OUT / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RTOS_TIMER_TESTS_PASS cases=2")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
