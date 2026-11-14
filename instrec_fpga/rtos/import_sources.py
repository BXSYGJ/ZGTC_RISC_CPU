"""Freeze the selected 125 MHz inputs and the pinned upstream RTOS sources.

This copies verified inputs; it never updates the original bitstream package.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
KERNEL_COMMIT = "89592801dd8b73329a7583719b7e3567b50910e5"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    package = ROOT / "build/pacerv_shared_system/selected_versions_20261114/125M_hold_clean"
    manifest = json.loads((package / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest["selection"]["system_clock_hz"] != 125000000:
        raise RuntimeError("The selected package is not the 125 MHz baseline")
    for record in manifest["files"]:
        if sha(package / record["path"]) != record["sha256"]:
            raise RuntimeError("Selected baseline changed: " + record["path"])
    inputs = json.loads((package / "INPUTS.json").read_text(encoding="utf-8"))
    records = []
    for record in inputs["files"]:
        source = package / "inputs" / record["path"]
        if sha(source) != record["sha256"]:
            raise RuntimeError("Frozen source changed: " + record["path"])
        target = HERE / "baseline125" / record["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError("Refusing to overwrite different frozen source: " + str(target))
        shutil.copyfile(source, target)
        records.append(record)
    (HERE / "baseline125/INPUTS.json").write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    (HERE / "baseline125/SOURCE_BUILD_RECIPE.tcl").write_bytes((package / "SOURCE_BUILD_RECIPE.tcl").read_bytes())
    baseline = {"original_run": manifest["selection"]["run"], "clock_hz": 125000000,
                "original_bitstream_sha256": manifest["selection"]["bitstream_sha256"],
                "original_package_manifest_sha256": sha(package / "PACKAGE_MANIFEST.json"),
                "source_count": len(records), "files": records}
    (HERE / "BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    upstream = ROOT / "build/rtos/upstream-kernel"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if commit != KERNEL_COMMIT:
        raise RuntimeError("Wrong upstream kernel commit: " + commit)
    paths = [Path(p) for p in ("tasks.c", "queue.c", "list.c", "timers.c", "event_groups.c",
                               "stream_buffer.c", "LICENSE.md", "README.md", "History.txt")]
    paths += [p.relative_to(upstream) for p in sorted((upstream / "include").glob("*.h"))]
    paths += [p.relative_to(upstream) for p in sorted((upstream / "portable/GCC/RISC-V").glob("*")) if p.is_file()]
    vendor_records = []
    for relative in paths:
        target = HERE / "vendor/FreeRTOS-Kernel" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upstream / relative, target)
        vendor_records.append({"path": relative.as_posix(), "sha256": sha(target), "bytes": target.stat().st_size})
    provenance = {"repository": "https://github.com/FreeRTOS/FreeRTOS-Kernel", "tag": "V11.3.3",
                  "commit": commit, "license": "MIT", "unmodified": True, "files": vendor_records}
    (HERE / "vendor/FreeRTOS-Kernel/PROVENANCE.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"RTOS_SOURCES_FROZEN baseline_files={len(records)} clock_hz=125000000 kernel_files={len(paths)} commit={commit}")


if __name__ == "__main__":
    main()
