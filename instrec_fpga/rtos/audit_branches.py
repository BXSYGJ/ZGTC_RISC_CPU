"""Record exact XSY/XSY2 source lineage used for the 125 MHz RTOS profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent
BRANCHES = {"XSY": "0b8201e071c6c59b8d7ead23ad944684f4d0b24c",
            "XSY2": "8f902aec29c38bc4a32a4e95ab47d18411684b52"}


def git_blob(commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", commit + ":instrec_fpga/" + path], cwd=REPO)


def main() -> None:
    common = ["src/npu/npu_m1_owner.v", "src/npu/npu_m1_bridge.v",
              "src/npu/weight_read_aligner_hardened.v", "sw/rv32/main.c",
              "sim/experiments/cpu_native_joint/native_owner.vh",
              "models/group5_v3_float_20261102/model_source.py",
              "models/group5_v3_float_20261102/float_state.npz",
              "models/group5_v3_float_20261102/reference_vectors.npz"]
    rows = []
    for path in common:
        values = {branch: git_blob(commit, path) for branch, commit in BRANCHES.items()}
        frozen = HERE / "baseline125" / path
        row = {"path": path, "sha256": {b: hashlib.sha256(v).hexdigest() for b, v in values.items()},
               "branches_identical": values["XSY"] == values["XSY2"],
               "baseline125_present": frozen.is_file()}
        if frozen.is_file():
            data = frozen.read_bytes()
            row["baseline125_sha256"] = hashlib.sha256(data).hexdigest()
            # Git checkout line endings may differ; retain both raw and semantic evidence.
            row["baseline_matches_normalized"] = {b: data.replace(b"\r\n", b"\n") == v.replace(b"\r\n", b"\n")
                                                   for b, v in values.items()}
        rows.append(row)
    report = {"repository": "https://github.com/BXSYGJ/ZGTC_RISC_CPU", "branches": BRANCHES,
              "baseline": "full-20261113-223256-full / 125 MHz",
              "integration": {"XSY": "125 MHz PaceRV full-system integration and immutable inference results",
                              "XSY2": "native M1 ownership, bridge/aligner and safe Mel-window CPU launch protocol",
                              "shared_model": "Five-group frozen source retained as application follow-up; existing eight-class accelerator geometry retained for this RTOS integration"},
              "files": rows}
    output = HERE / "evidence/BRANCH_REUSE.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"RTOS_BRANCH_AUDIT_PASS branches=2 files={len(rows)} shared_identical={sum(r['branches_identical'] for r in rows)}")


if __name__ == "__main__":
    main()
