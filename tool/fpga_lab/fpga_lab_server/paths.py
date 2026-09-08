import os
from pathlib import Path

BASE = Path(__file__).resolve().parent                    # .../fpga_lab/fpga_lab_server
PROJECT = BASE.parent                                      # .../fpga_lab
TOOL = PROJECT.parent                                      # .../Pango/tool

# account file can be overridden for other machines via env var
ACCOUNT_FILE = Path(os.environ.get("FPGA_LAB_ACCOUNT", TOOL / "account.txt"))


def account_creds() -> list[str]:
    if not ACCOUNT_FILE.exists():
        raise FileNotFoundError(f"account file not found: {ACCOUNT_FILE}")
    lines = [ln.strip() for ln in ACCOUNT_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError(f"account file {ACCOUNT_FILE} must contain email and password lines")
    return lines
