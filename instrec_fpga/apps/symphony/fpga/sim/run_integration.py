"""Verify actual KEY1 gestures through symphony_state into native HDMI pixels."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
FPGA = HERE.parent
ROOT = FPGA.parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    out = ROOT / "build/symphony/integration" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True, exist_ok=False)
    assets = [FPGA / "assets" / name for name in
              ("symphony_font.hex", "symphony_guide.hex", "symphony_library.hex")]
    sources = [FPGA / "symphony_state.v", FPGA / "symphony_renderer.v",
               HERE / "tb_symphony_integration.sv", Path(__file__),
               *assets, FPGA / "assets/ASSETS.json"]
    frozen = []
    for path in sources:
        target = out / "inputs" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        frozen.append(target)
    iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iv or not vvp:
        raise RuntimeError("Native Icarus and vvp are required")
    report = {"passed": False, "started_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Real state + renderer + real font/tile ROMs; actual physical-key pin gestures; accelerated ms divider only; RGB/DE/HS/VS checked at five pipeline stages",
              "source_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in sources},
              "input_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in frozen},
              "commands": []}
    try:
        image = out / "integration.vvp"
        definitions = ['-DSYMPHONY_' + name + '_HEX="' + path.as_posix() + '"'
                       for name, path in zip(("FONT", "GUIDE", "LIBRARY"), frozen[4:7])]
        commands = [[iv, "-g2005-sv", "-s", "tb_symphony_integration", "-o", str(image),
                     *definitions, *map(str, frozen[:3])], [vvp, "-i", str(image)]]
        for index, command in enumerate(commands):
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=60,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            output = process.stdout + process.stderr
            log = out / ("compile.log" if index == 0 else "simulation.log")
            log.write_text(output, encoding="utf-8")
            report["commands"].append({"command": command, "cwd": str(ROOT), "exit_code": process.returncode,
                                       "output": output, "log": str(log), "sha256": sha(log)})
            if process.returncode or (index == 1 and "SYMPHONY_INTEGRATION_PASS" not in output):
                raise RuntimeError(output)
            if index == 1:
                report["pixel_samples"] = [dict(x=int(x), y=int(y), rgb=rgb) for x,y,rgb in re.findall(
                    r"SYMPHONY_PIXEL x=(\d+) y=(\d+) rgb=([0-9a-f]{6})", output)]
                print(output, end="")
        report["sources_unchanged"] = all(sha(path) == report["source_sha256"][path.relative_to(ROOT).as_posix()] for path in sources)
        report["inputs_unchanged"] = all(sha(path) == report["input_sha256"][path.relative_to(ROOT).as_posix()] for path in frozen)
        report["passed"] = report["sources_unchanged"] and report["inputs_unchanged"]
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        body = json.dumps(report, indent=2) + "\n"
        (out / "RESULT.json").write_text(body, encoding="utf-8")
        (out.parent / "RESULTS.json").write_text(body, encoding="utf-8")
    print("SYMPHONY_INTEGRATION_REPORT " + str(out / "RESULT.json"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
