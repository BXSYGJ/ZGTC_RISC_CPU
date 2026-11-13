"""Compile a frozen clock candidate in an isolated, memory-gated PDS project."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    manifest = json.loads((candidate / "INPUTS.json").read_text(encoding="utf-8"))
    check = subprocess.run([
        "pwsh", "-NoProfile", "-Command",
        "if ((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 2097152) { exit 3 }",
    ], creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    if check.returncode:
        raise RuntimeError("Compile-only candidate needs at least 2 GiB currently available memory")
    for item in manifest["files"]:
        source = candidate / "inputs" / item["path"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Frozen input mismatch: " + item["path"])
    work = candidate / "compile_only"
    work.mkdir(exist_ok=False)
    recipe = (candidate / "build.tcl").read_text(encoding="utf-8")
    lines = recipe.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("synthesize "))
    script = work / "compile_only.tcl"
    script.write_text("\n".join(lines[:index] + ["exit"]) + "\n", encoding="utf-8")
    pds = Path(os.environ.get("PDS_ROOT", "D:/PDS_2022.2-SP6.4")) / "bin/pds_shell.exe"
    command = [str(pds), "-file", str(script), "-work_dir", str(work),
               "-project_name", "pacerv_clock_compile"]
    started = time.monotonic()
    with (work / "pds.stdout.log").open("wb") as stream:
        process = subprocess.Popen(command, cwd=work, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        print("CLOCK_COMPILE_PID " + str(process.pid), flush=True)
        code = process.wait()
    text = (work / "pds.stdout.log").read_text(encoding="utf-8", errors="replace")
    unchanged = all(hashlib.sha256((candidate / "inputs" / item["path"]).read_bytes()).hexdigest()
                    == item["sha256"] for item in manifest["files"])
    errors = [line for line in text.splitlines() if re.match(r"^E:", line)]
    passed = code == 0 and not errors and unchanged and bool(re.search(
        r"Executing\s*:\s*compile\b[^\r\n]*successfully\.", text))
    report = {"command": command, "exit_status": code, "errors": errors,
              "seconds": time.monotonic() - started, "frozen_inputs_unchanged": unchanged,
              "passed": passed, "scope": "Compile only; no synthesis, routing or timing qualification"}
    (candidate / "CLOCK_COMPILE_RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("CLOCK_COMPILE_" + ("PASS" if passed else "FAIL") + " " + str(candidate), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
