"""Freeze the pre-integration inputs from Git, without touching working files."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
BASELINE = "852f067db4a4a710f5355e3ab311f035ced5b48d"
FILES = [
    "instrec_fpga/src/ctrl/instrec_top.v",
    "instrec_fpga/src/cpu/rv32_cpu_subsys.sv",
    "instrec_fpga/src/cpu/prog.hex",
    "instrec_fpga/src/ddr3/ddr3_ctrl_axi.v",
    "instrec_fpga/src/ddr3/ddr3_arbiter.v",
    "instrec_fpga/scripts/build_sets.json",
    "instrec_fpga/sim/run_sim.py",
    "instrec_fpga/sim/tb_rv_cpu.sv",
    "instrec_fpga/sw/rv32/main.c",
    "instrec_fpga/sw/rv32/start.S",
    "instrec_fpga/sw/rv32/link.ld",
    "instrec_fpga/src/npu/activation_store_mux.v",
    "instrec_fpga/src/npu/activation_row_store_dynamic.v",
    "instrec_fpga/src/npu/fc_engine.v",
    "instrec_fpga/src/npu/weight_read_aligner_hardened.v",
    "instrec_fpga/src/npu/wdma.v",
    "instrec_fpga/src/npu/gap_unit.v",
    "instrec_fpga/src/ctrl/weight_loader.v",
    "instrec_fpga/ipcore/ddr3_test/ddr3_test.idf",
    "instrec_fpga/ipcore/ddr3_test/ddr3_test.v",
    "instrec_fpga/ipcore/ddr3_test/ddr3_test_ddrphy_top.v",
    "instrec_fpga/constraints/ddr3_100h.fdc",
    "instrec_fpga/src/ui/dashboard_renderer.v",
    "instrec_fpga/src/ui/dashboard_text.v",
    "instrec_fpga/sim/tb_dashboard_ui.sv",
] + ["cpu/rtl/rv32_" + name + ".sv" for name in
     ("core", "alu", "decode", "muldiv", "btb", "machine")]


def main() -> None:
    out = ROOT / "build/pacerv_shared_system/baseline/source"
    records = []
    for relative in FILES:
        content = subprocess.check_output(
            ["git", "show", BASELINE + ":" + relative], cwd=REPO)
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise RuntimeError("Existing baseline differs: " + str(target))
        target.write_bytes(content)
        records.append({"path": relative, "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {"baseline_commit": BASELINE, "files": records}
    target = Path(__file__).with_name("BASELINE_MANIFEST.json")
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == manifest
    print("BASELINE_SNAPSHOT_OK files=" + str(len(records)))


if __name__ == "__main__":
    main()
