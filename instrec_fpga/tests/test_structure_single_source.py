"""Structural guards: duplicated files that must stay byte-identical.

These tests do not exercise RTL or builds. They only protect structural
invariants that are easy to break during cleanup/migration:

1. DDR3 pin constraints exist in two projects and must stay identical.
2. The SDD documents are mirrored into .codeartsdoer/specs and must match.

If a copy is intentionally changed, update both copies in the same commit.
"""

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ddr3_pin_constraints_copies_are_identical():
    """instrec_fpga and pds_cpu_100h must use the same DDR3 pin contract."""
    instrec = REPO_ROOT / "instrec_fpga" / "constraints" / "ddr3_100h.fdc"
    cpu100h = REPO_ROOT / "pds_cpu_100h" / "constraints" / "ddr3_100h.fdc"

    assert instrec.is_file(), f"missing DDR3 constraints: {instrec}"
    assert cpu100h.is_file(), f"missing DDR3 constraints: {cpu100h}"
    assert _sha256(instrec) == _sha256(cpu100h), (
        "DDR3 pin constraints drifted between instrec_fpga and pds_cpu_100h; "
        "update both copies together"
    )


def test_sdd_documents_match_codeartsdoer_mirror():
    """docs/sdd is authoritative; .codeartsdoer/specs is a byte-identical mirror."""
    sdd_dir = REPO_ROOT / "instrec_fpga" / "docs" / "sdd"
    mirror_dir = REPO_ROOT / ".codeartsdoer" / "specs" / "instrec_fpga"

    if not mirror_dir.is_dir():
        pytest.skip(".codeartsdoer mirror is not present in this workspace")

    for name in ("spec.md", "design.md", "tasks.md"):
        sdd = sdd_dir / name
        mirror = mirror_dir / name
        assert sdd.is_file(), f"missing SDD file: {sdd}"
        assert mirror.is_file(), f"missing SDD mirror: {mirror}"
        assert _sha256(sdd) == _sha256(mirror), (
            f"{name} drifted between docs/sdd and .codeartsdoer; "
            "docs/sdd is authoritative, refresh the mirror"
        )
