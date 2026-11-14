"""Read all 4096 ROM words through the real wrapper fetch and data buses."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from rom_banks import validate_banks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", type=Path, default=ROOT / "build/rtos/firmware/prog.hex")
    args = parser.parse_args()
    full = args.firmware.resolve(strict=True)
    even, odd = full.with_name(full.stem + "_even.hex"), full.with_name(full.stem + "_odd.hex")
    validate_banks(full, even, odd, 4096)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out = ROOT / "build/rtos/rom_readout" / stamp
    inputs = [full, even, odd, HERE / "tb_rom_readout.sv",
              ROOT / "rtos/rtl/rv32_cpu_subsys.sv", ROOT / "rtos/rtl/machine_timer.v"]
    inputs += sorted((ROOT / "rtos/baseline125/src/cpu/vendor/pacerv_h3").glob("*.sv"))
    frozen = {}
    for source in inputs:
        relative = source.relative_to(ROOT)
        target = out / "inputs" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        frozen[source] = target
    report = {"scope": "actual direct-readmemh ROM arrays, synchronous fetch/data paths, all 4096 words",
              "commands": [], "passed": False,
              "input_sha256": {str(p.relative_to(ROOT)): digest(frozen[p]) for p in inputs}}

    def run(command: list[str | Path]) -> dict:
        argv = [str(item) for item in command]
        process = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=120)
        record = {"command": argv, "cwd": str(ROOT), "exit_status": process.returncode,
                  "output": process.stdout + process.stderr}
        report["commands"].append(record)
        if process.returncode:
            raise RuntimeError(record["output"])
        return record

    try:
        iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
        if not iv or not vvp:
            raise RuntimeError("Native Icarus Verilog is required")
        image = out / "tb_rom_readout.vvp"
        definitions = [f'-D{name}="{frozen[path].as_posix()}"' for name, path in
                       (("ROM_PROG_HEX", full), ("ROM_EVEN_HEX", even), ("ROM_ODD_HEX", odd))]
        run([iv, "-g2012", "-s", "tb_rom_readout", "-o", image, *definitions,
             *[frozen[p] for p in inputs[3:]]])
        execution = run([vvp, "-i", image])
        print(execution["output"], end="")
        report["inputs_unchanged"] = all(digest(frozen[p]) == report["input_sha256"][str(p.relative_to(ROOT))]
                                         for p in inputs)
        report["passed"] = "ROM_READOUT_PASS words=4096" in execution["output"] and report["inputs_unchanged"]
    finally:
        (out / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        summary = ROOT / "build/rtos/rom_readout/RESULTS.json"
        summary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("ROM_READOUT_EVIDENCE=" + str(out / "RESULT.json"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
