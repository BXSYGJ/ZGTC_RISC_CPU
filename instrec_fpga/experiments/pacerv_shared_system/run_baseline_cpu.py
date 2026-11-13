"""Reproduce the original control-CPU measurement from the frozen Git input."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
subprocess.run([sys.executable, str(Path(__file__).with_name("capture_baseline.py"))], check=True)
baseline = ROOT / "build/pacerv_shared_system/baseline/source"
manifest = json.loads(Path(__file__).with_name("BASELINE_MANIFEST.json").read_text(encoding="utf-8"))
for entry in manifest["files"]:
    if hashlib.sha256((baseline / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
        raise RuntimeError("Frozen baseline changed: " + entry["path"])
iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
if not iv or not vvp:
    raise RuntimeError("Put Icarus iverilog and vvp on PATH")
out = ROOT / "build/pacerv_shared_system/baseline"
sources = [baseline / "instrec_fpga/sim/tb_rv_cpu.sv", baseline / "instrec_fpga/src/cpu/rv32_cpu_subsys.sv"]
sources += [baseline / "cpu/rtl" / ("rv32_" + name + ".sv")
            for name in ("core", "alu", "decode", "muldiv", "btb", "machine")]
records = []
for command in ([iv, "-g2012", "-s", "tb_rv_cpu", "-o", str(out / "verified_cpu.vvp"), *map(str, sources)],
                [vvp, "-i", str(out / "verified_cpu.vvp")]):
    process = subprocess.run(command, cwd=baseline / "instrec_fpga", capture_output=True, timeout=120)
    output = (process.stdout + process.stderr).decode("utf-8", errors="replace")
    records.append({"command": command, "cwd": str(baseline / "instrec_fpga"),
                    "exit_status": process.returncode, "output": output})
    if process.returncode:
        raise RuntimeError(output)
passed = "RESULT: PASS" in records[-1]["output"] and "RESULT: FAIL" not in records[-1]["output"]
result = {"baseline_commit": manifest["baseline_commit"], "verified_source_count": len(manifest["files"]),
          "passed": passed, "commands": records}
(out / "BASELINE_CPU_RESULTS.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
(out / "BASELINE_CPU_OUTPUT.txt").write_text(records[-1]["output"], encoding="utf-8")
print(records[-1]["output"])
raise SystemExit(0 if passed else 1)
