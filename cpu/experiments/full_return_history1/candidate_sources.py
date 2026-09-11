from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_raw_relation_payload"
BASE = ROOT.parent / "full_redirect_clock151200"
OVERRIDES = ("rtl/rv32_core.sv", "rtl/rv32_btb.sv")


def source_path(relative):
    return ROOT / Path(relative).name if relative in OVERRIDES else BASE / relative
