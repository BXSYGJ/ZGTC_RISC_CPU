"""Freeze and simulate the real HDMI history / KEY1 RTL with native Icarus."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    out = ROOT / "build/symphony/state" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True, exist_ok=False)
    sources = [HERE.parent / "symphony_state.v", HERE / "tb_symphony_state.sv", Path(__file__)]
    frozen = []
    for source in sources:
        target = out / "inputs" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        frozen.append(target)
    iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iv or not vvp:
        raise RuntimeError("Native Icarus and vvp are required")
    report = {"passed": False, "started_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Actual symphony_state RTL; 10 clocks per simulated millisecond, real gesture durations 900/300 ms; production divider defaults to 148500000 Hz",
              "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in sources},
              "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in frozen},
              "commands": []}
    try:
        image = out / "state.vvp"
        for index, command in enumerate([
            [iv, "-g2005-sv", "-s", "tb_symphony_state", "-o", str(image), *map(str, frozen[:2])],
            [vvp, "-i", str(image)],
        ]):
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=60,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            output = process.stdout + process.stderr
            log = out / ("compile.log" if index == 0 else "simulation.log")
            log.write_text(output, encoding="utf-8")
            report["commands"].append({"command": command, "cwd": str(ROOT), "output": output,
                                       "exit_code": process.returncode, "log": str(log), "sha256": digest(log)})
            if process.returncode or (index == 1 and "SYMPHONY_STATE_PASS" not in output):
                raise RuntimeError(output)
            if index == 1:
                print(output, end="")
        report["inputs_unchanged"] = all(digest(path) == report["input_sha256"][str(path.relative_to(ROOT))] for path in frozen)
        report["sources_unchanged"] = all(digest(path) == report["source_sha256"][str(path.relative_to(ROOT))] for path in sources)
        report["passed"] = report["inputs_unchanged"] and report["sources_unchanged"]
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        body = json.dumps(report, indent=2) + "\n"
        (out / "RESULT.json").write_text(body, encoding="utf-8")
        (out.parent / "RESULTS.json").write_text(body, encoding="utf-8")
    print("SYMPHONY_STATE_REPORT " + str(out / "RESULT.json"))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
