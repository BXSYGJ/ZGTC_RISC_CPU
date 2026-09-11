from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_raw_relation_payload"
BASE = ROOT.parent / "full_redirect_clock151200"
OVERRIDES = ("rtl/rv32_core.sv", "rtl/rv32_btb.sv", "rtl/rv32_cache.sv")


def source_path(relative):
    if relative == "rtl/rv32_cache.sv":
        return ROOT / "rv32_cache.sv"
    if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv"):
        return PARENT / Path(relative).name
    return BASE / relative
