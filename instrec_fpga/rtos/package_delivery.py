"""Package an audited 125 MHz RTOS bitstream, firmware and frozen project."""
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
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pds-run", type=Path, required=True)
    args = ap.parse_args()
    run = args.pds_run.resolve(strict=True)
    # Reopen accepted sources, firmware outputs, mapped ROM, implementation
    # controls and reports immediately before copying the delivery snapshot.
    subprocess.run([sys.executable, "-X", "utf8", str(HERE / "collect_evidence.py"),
                    "--pds-run", str(run), "--require-complete"], cwd=ROOT, check=True)
    acceptance = json.loads((HERE / "evidence/ACCEPTANCE.json").read_text(encoding="utf-8"))
    if not all(acceptance["gates"].values()) or Path(acceptance["pds_run"]).resolve() != run:
        raise RuntimeError("Complete the source, functional and bitstream audit first")
    full = json.loads((run / "FULL_RESULT.json").read_text(encoding="utf-8"))
    bit = Path(full["bitstream"]["path"])
    if full["status"] != "pass" or sha(bit) != full["bitstream"]["sha256"]:
        raise RuntimeError("The FPGA bitstream is not the audited implementation")
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "build/rtos/releases" / ("rtos125-" + stamp)
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(bit, out / "instrec_top_rtos125.sbit")
    shutil.copyfile(run / "report_timing/instrec_top.rtr", out / "TIMING.rtr")
    shutil.copyfile(run / "INPUTS.json", out / "INPUTS.json")
    shutil.copyfile(run / "FULL_RESULT.json", out / "BUILD_RESULT.json")
    shutil.copytree(run / "inputs", out / "inputs")
    for name in ("prog.hex", "prog_even.hex", "prog_odd.hex", "prog.bin", "prog.elf", "prog.map", "prog.dis", "BUILD.json", "SIZE.txt"):
        target = out / "firmware" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(ROOT / "build/rtos/firmware" / name, target)
    shutil.copytree(HERE, out / "rtos", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    recipe = (run / "build.tcl").read_text(encoding="utf-8")
    recipe = recipe.replace((run / "inputs").as_posix() + "/", "inputs/")
    # The map recipe omits implementation. Add the exact accepted commands.
    lines = recipe.splitlines()
    if lines[-1] != "exit":
        raise RuntimeError("Unexpected original build recipe terminator")
    lines = lines[:-1] + [full["pnr_command"], "report_timing", "gen_bit_stream", "exit"]
    (out / "REBUILD.tcl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for path in (out / "inputs").rglob("*.hex"):
        target = out / path.relative_to(out / "inputs")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    copied = json.loads((out / "INPUTS.json").read_text(encoding="utf-8"))
    for item in copied["files"]:
        if sha(out / "inputs" / item["path"]) != item["sha256"]:
            raise RuntimeError("Copied frozen input differs from the accepted build: " + item["path"])
    firmware_build = json.loads((out / "firmware/BUILD.json").read_text(encoding="utf-8"))
    for item in firmware_build["outputs"]:
        if sha(out / "firmware" / item["name"]) != item["sha256"]:
            raise RuntimeError("Copied firmware differs from its accepted build: " + item["name"])
    if sha(out / "TIMING.rtr") != full["timing_report"]["sha256"] or sha(out / "INPUTS.json") != full["manifest_sha256"]:
        raise RuntimeError("Copied implementation metadata differs from the accepted reports")
    note = ["125 MHz InstRec + FreeRTOS V11.3.3", "", "Bitstream: instrec_top_rtos125.sbit",
            "System clock: 125000000 Hz; RTOS tick: 1000 Hz; ROM/RAM: 16 KiB / 16 KiB.",
            "The original audio/Mel/native 8-class NPU/HDMI pipeline is retained.",
            "Source, complete frozen inputs, firmware ELF/HEX, original timing report and test evidence are included.",
            "Run PDS from this directory with REBUILD.tcl to resolve relative ROM paths.",
            "RTOS source and normal verification commands are documented in rtos/README.md; use those within the repository.",
            "Timing values are retained verbatim in TIMING.rtr. No timing-closure claim is made.",
            "Board testing has not run: the workstation did not enumerate FTDI/CP2102 devices at preflight.",
            "Original 125 MHz rollback inputs remain in rtos/baseline125; PowerShell rollback entry is rtos/ROLLBACK.ps1."]
    (out / "README.txt").write_text("\n".join(note) + "\n", encoding="utf-8")
    files = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
             for p in sorted(out.rglob("*")) if p.is_file()]
    manifest = {"clock_hz": 125000000, "tick_hz": 1000, "bitstream_sha256": sha(bit),
                "baseline_run": "full-20261113-223256-full", "files": files}
    (out / "PACKAGE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive = out.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        reopened = json.loads(z.read("PACKAGE_MANIFEST.json").decode("utf-8"))
        for record in reopened["files"]:
            data = z.read(record["path"])
            if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise RuntimeError("Package verification failed: " + record["path"])
    delivery = {"directory": str(out), "archive": str(archive), "archive_sha256": sha(archive),
                "bitstream": str(out / "instrec_top_rtos125.sbit"), "bitstream_sha256": sha(bit),
                "file_count": len(files) + 1, "archive_reopened_all_hashes_pass": True,
                "board_test_executed": False}
    (HERE / "evidence/DELIVERY.json").write_text(json.dumps(delivery, indent=2) + "\n", encoding="utf-8")
    print("RTOS125_PACKAGE_PASS files=" + str(len(files)+1) + " zip=" + str(archive))


if __name__ == "__main__":
    main()
