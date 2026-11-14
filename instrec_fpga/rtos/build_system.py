"""Build a complete 125 MHz InstRec + FreeRTOS system from frozen inputs.

No source in the selected bitstream package or the active legacy tree changes.
Use --stage prepare to review the complete project without starting PDS.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ROM_IMAGES = (("prog.hex", "prog_pacerv.hex"),
              ("prog_even.hex", "prog_pacerv_even.hex"),
              ("prog_odd.hex", "prog_pacerv_odd.hex"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources() -> dict:
    baseline = json.loads((HERE / "BASELINE.json").read_text(encoding="utf-8"))
    for record in baseline["files"]:
        path = HERE / "baseline125" / record["path"]
        if sha(path) != record["sha256"]:
            raise RuntimeError("Frozen 125 MHz source changed: " + str(path))
    vendor = HERE / "vendor/FreeRTOS-Kernel"
    provenance = json.loads((vendor / "PROVENANCE.json").read_text(encoding="utf-8"))
    for record in provenance["files"]:
        if sha(vendor / record["path"]) != record["sha256"]:
            raise RuntimeError("Upstream kernel source changed: " + record["path"])
    return baseline


def prepare(stage: str, label: str) -> Path:
    baseline = verify_sources()
    firmware = ROOT / "build/rtos/firmware/prog.hex"
    if not firmware.is_file():
        raise FileNotFoundError("Build the production firmware first: rtos/build_firmware.py")
    build = json.loads((firmware.parent / "BUILD.json").read_text(encoding="utf-8"))
    # The application build must retain the real 1 kHz timer, not the test image.
    if build.get("test", build.get("test_mode", False)):
        raise RuntimeError("A test firmware cannot be packaged as the board application")
    for record in build["inputs"]:
        if sha(ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError("Firmware source changed; rebuild first: " + record["path"])
    binary = firmware.parent / "prog.bin"
    if sha(binary) != build["binary_sha256"]:
        raise RuntimeError("Firmware binary changed after compilation")
    data = binary.read_bytes()
    padded = data + bytes((-len(data)) % 4)
    expected_hex = "".join(f"{int.from_bytes(padded[n:n+4], 'little'):08x}\n"
                           for n in range(0, len(padded), 4))
    if firmware.read_text(encoding="ascii") != expected_hex:
        raise RuntimeError("Firmware ROM image does not match the linked binary")
    words = expected_hex.splitlines()
    for filename, parity in (("prog_even.hex", 0), ("prog_odd.hex", 1)):
        expected_bank = "".join(word + "\n" for word in words[parity::2])
        if (firmware.parent / filename).read_text(encoding="ascii") != expected_bank:
            raise RuntimeError("Firmware instruction bank does not match the linked binary: " + filename)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "build/rtos/pds" / (stamp + "-" + label + "-" + stage)
    out.mkdir(parents=True, exist_ok=False)
    inputs = out / "inputs"
    shutil.copytree(HERE / "baseline125", inputs)
    for name in ("rv32_cpu_subsys.sv", "machine_timer.v"):
        shutil.copyfile(HERE / "rtl" / name, inputs / "src/cpu" / name)
    top = inputs / "src/ctrl/instrec_top.v"
    text = top.read_text(encoding="utf-8")
    marker = '.PROG_HEX         ("src/cpu/prog_pacerv.hex")'
    if text.count(marker) != 1:
        raise RuntimeError("Unexpected baseline CPU instantiation")
    text = text.replace(marker, '.IMEM_WORDS       (4096),\n        .DMEM_WORDS       (4096),\n        '
                        '.PROG_EVEN_HEX   ("src/cpu/prog_pacerv_even.hex"),\n        '
                        '.PROG_ODD_HEX    ("src/cpu/prog_pacerv_odd.hex"),\n        ' + marker)
    top.write_text(text, encoding="utf-8")
    for source, target in ROM_IMAGES:
        shutil.copyfile(firmware.parent / source, inputs / "src/cpu" / target)
    recipe = (HERE / "baseline125/SOURCE_BUILD_RECIPE.tcl").read_text(encoding="utf-8")
    match = re.search(r'add_design "(.+?)/inputs/', recipe)
    if not match:
        raise RuntimeError("Missing frozen-source prefix")
    recipe = recipe.replace(match.group(1) + "/inputs/", inputs.as_posix() + "/")
    recipe = recipe.replace("set_arch ", f'add_design "{(inputs / "src/cpu/machine_timer.v").as_posix()}"\nset_arch ', 1)
    lines = recipe.splitlines()
    if stage in ("prepare", "compile"):
        lines = lines[:next(i for i, s in enumerate(lines) if s.startswith("synthesize"))] + ["exit"]
    elif stage in ("map", "full"):
        # Inspect actual mapped ROM initialization before implementation.
        lines = lines[:next(i for i, s in enumerate(lines) if s.startswith("pnr"))] + ["exit"]
    # Relative readmemh paths are resolved from the PDS working directory.
    for path in inputs.rglob("*.hex"):
        target = out / path.relative_to(inputs)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (out / "build.tcl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    params = {p.findtext("name"): p.findtext("value") for p in ET.parse(
        inputs / "ipcore/ddr3_test/ddr3_test.idf").findall("./param_list/param")}
    clock = round(float(params["ACTUAL_RATE"]) * 1e6 / 8)
    if clock != 125000000:
        raise RuntimeError("DDR user clock is not 125 MHz")
    records = [{"path": p.relative_to(inputs).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
               for p in sorted(inputs.rglob("*")) if p.is_file()]
    changed = []
    for item in baseline["files"]:
        if sha(inputs / item["path"]) != item["sha256"]:
            changed.append(item["path"])
    manifest = {"scope": "complete PG100 125 MHz audio/mel/native NPU/HDMI/FreeRTOS system",
                "stage": stage, "target": "PG2L100H-6IFBG676", "system_clock_hz": clock,
                "pixel_clock_hz": 148500000, "tick_hz": 1000, "rom_bytes": 16384, "ram_bytes": 16384,
                "baseline_run": baseline["original_run"], "baseline_files": baseline["source_count"],
                "changed_baseline_files": changed, "added_rtl": ["src/cpu/machine_timer.v"],
                "added_rom_images": ["src/cpu/" + target for _, target in ROM_IMAGES[1:]],
                "firmware_hex_sha256": sha(firmware),
                "firmware_rom_images": [{"path": "src/cpu/" + target, "sha256": sha(firmware.parent / source)}
                                        for source, target in ROM_IMAGES],
                "rom_initialization": "direct readmemh into actual parity instruction banks and data ROM",
                "files": records}
    (out / "INPUTS.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("RTOS_SYSTEM_PREPARED " + str(out), flush=True)
    return out


def run(out: Path, minutes: int) -> None:
    probe = subprocess.run(["pwsh", "-NoProfile", "-Command",
        "if (Get-Process -Name pds_shell -ErrorAction SilentlyContinue) { exit 2 }"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if probe.returncode:
        raise RuntimeError("A PDS flow is already running")
    pds = Path(os.environ.get("PDS_ROOT", "D:/PDS_2022.2-SP6.4")) / "bin/pds_shell.exe"
    if not pds.is_file():
        raise FileNotFoundError(pds)
    command = [str(pds), "-file", str(out / "build.tcl"), "-work_dir", str(out), "-project_name", "instrec_rtos_125"]
    start = time.monotonic()
    with (out / "pds.stdout.log").open("wb") as stdout, (out / "pds.stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, cwd=out, stdout=stdout, stderr=stderr,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        (out / "PROCESS.json").write_text(json.dumps({"pid": process.pid, "command": command}, indent=2), encoding="utf-8")
        print("RTOS_PDS_PID " + str(process.pid), flush=True)
        try:
            code = process.wait(timeout=minutes * 60)
        except subprocess.TimeoutExpired:
            process.terminate()
            code = process.wait(timeout=30)
            raise RuntimeError("RTOS PDS build exceeded the requested time limit")
    output = (out / "pds.stdout.log").read_text(encoding="utf-8", errors="replace")
    output += (out / "pds.stderr.log").read_text(encoding="utf-8", errors="replace")
    stages = {s: bool(re.search(r"Executing\s*:\s*" + s + r"\b[^\r\n]*successfully\.", output))
              for s in ("compile", "synthesize", "dev_map", "pnr", "report_timing", "gen_bit_stream")}
    errors = [s for s in output.splitlines() if s.startswith("E:") and "SCBV has not been set" not in s and "Bitstream-2001" not in s]
    manifest = json.loads((out / "INPUTS.json").read_text(encoding="utf-8"))
    unchanged = all(sha(out / "inputs" / r["path"]) == r["sha256"] for r in manifest["files"])
    result = {"command": command, "exit_code": code, "seconds": round(time.monotonic()-start, 3),
              "stages": stages, "errors": errors, "frozen_inputs_unchanged": unchanged}
    (out / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    needed = {"compile": ["compile"], "map": ["compile", "synthesize", "dev_map"],
              "full": ["compile", "synthesize", "dev_map"]}[manifest["stage"]]
    if code or errors or not unchanged or not all(stages[s] for s in needed):
        raise RuntimeError("RTOS PDS build failed; inspect " + str(out / "RESULT.json"))
    print("RTOS_PDS_PASS stage=" + ("map" if manifest["stage"] == "full" else manifest["stage"]), flush=True)
    if manifest["stage"] in ("map", "full"):
        subprocess.run([sys.executable, "-X", "utf8", str(HERE / "audit_mapped_rom.py"),
                        "--pds-run", str(out)], cwd=ROOT, check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if manifest["stage"] == "full":
        subprocess.run([sys.executable, "-X", "utf8", str(HERE / "continue_implementation.py"),
                        "--run-dir", str(out), "--minutes", str(min(minutes, 120))],
                       cwd=ROOT, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=("prepare", "compile", "map", "full"), default="prepare")
    ap.add_argument("--label", default="rtos")
    ap.add_argument("--minutes", type=int, default=90)
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", args.label) or not 1 <= args.minutes <= 240:
        raise ValueError("Invalid build label or time limit")
    out = prepare(args.stage, args.label)
    if args.stage != "prepare":
        run(out, args.minutes)


if __name__ == "__main__":
    main()
