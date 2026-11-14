#!/usr/bin/env python3
"""Flash an InstRec bitstream over JTAG.

The USB Cable II drops off the bus every few hours (PnP "Unknown", cdt_cfg says
"No PANGO USB CABLE II cable was found in system"); a physical replug is the
only cure.  This script is the flashing entry point:

  1. make sure one jtagserver is listening on 127.0.0.1:65420 (start it if it
     is missing, NEVER kill an existing one -- the project rule);
  2. run cdt_cfg with a generated TCL that points at the requested .sbit;
  3. retry a few times when the cable or the chain is missing (a retry after a
     few seconds often succeeds on its own);
  4. fail loudly if the device never acknowledges the programming.

Usage
-----
    python scripts/flash_bitstream.py                      # build/instrec-latest.sbit
    python scripts/flash_bitstream.py --sbit build/pds/<run>/generate_bitstream/instrec_top.sbit
    python scripts/flash_bitstream.py --status-only          # scan the chain only

Exit codes: 0 programmed, 1 tool/flow error, 2 the cable never came back.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

DEFAULT_SBIT = ROOT / "build" / "instrec-latest.sbit"
HOST = "127.0.0.1"
PORT = "65420"

TCL_TEMPLATE = """cfg_set_tcl_break -flag false
cfg_connect -ip %(host)s -port %(port)s
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
cfg_assign_file -file %(sbit)s -device_index 0
cfg_program -device_index 0
cfg_disconnect
puts "PROGRAM FLOW DONE"
exit
"""

SCAN_TEMPLATE = """cfg_set_tcl_break -flag false
cfg_connect -ip %(host)s -port %(port)s
cfg_set_cable_property -index 0 -freq 10Mhz
cfg_scan_chain
cfg_disconnect
exit
"""


def pds_bin(name: str) -> Path:
    root = os.environ.get("PDS_ROOT") or r"H:\GG\pango\PDS_2022.2-SP6.4"
    exe = Path(root) / "bin" / name
    if not exe.is_file():
        raise SystemExit("PDS tool not found: %s (set PDS_ROOT)" % exe)
    return exe


def _listening() -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, int(PORT))) == 0


def ensure_jtagserver() -> bool:
    """Start the jtagserver when nobody listens.  Never touches a live one."""
    if _listening():
        return False
    exe = pds_bin("cdt_js.exe")
    subprocess.Popen([str(exe), "-port", PORT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    for _ in range(30):
        if _listening():
            return True
        time.sleep(0.5)
    raise SystemExit("jtagserver did not start on %s:%s" % (HOST, PORT))


def run_cdt_cfg(sbit: Path, keep_tcl: bool = False,
                scan_only: bool = False) -> tuple[int, str]:
    tcl = ROOT / "build" / ("flash_%d.tcl" % int(time.time() * 1000))
    tcl.parent.mkdir(parents=True, exist_ok=True)
    text = SCAN_TEMPLATE if scan_only else TCL_TEMPLATE
    tcl.write_text(text % {"host": HOST, "port": PORT,
                           "sbit": str(sbit).replace("\\", "/")},
                   encoding="ascii")
    try:
        out = subprocess.run([str(pds_bin("cdt_cfg.exe")), "-file", str(tcl)],
                             capture_output=True, text=True)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    finally:
        if not keep_tcl:
            tcl.unlink(missing_ok=True)


CABLE_MISSING = ("No PANGO USB CABLE II cable was found",
                 "There is no device in Jtag chain",
                 "No devices detected while scanning the JTAG chain",
                 "Fail to open PANGO USB CABLE II cable",
                 "Fail to write instruction or data")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sbit", default=str(DEFAULT_SBIT))
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--keep-tcl", action="store_true")
    ap.add_argument("--status-only", action="store_true",
                    help="only connect + scan the chain; never reconfigures the FPGA")
    args = ap.parse_args(argv)

    sbit = Path(args.sbit)
    if not args.status_only and not sbit.is_file():
        print("bitstream not found: %s" % sbit, file=sys.stderr)
        return 1

    if not args.status_only:
        print("bitstream : %s (%d B)" % (sbit, sbit.stat().st_size))
    if ensure_jtagserver():
        print("jtagserver: started")
    else:
        print("jtagserver: reusing the running instance")

    attempts = max(1, args.retries)
    for attempt in range(1, attempts + 1):
        rc, text = run_cdt_cfg(sbit, args.keep_tcl, args.status_only)
        missing = any(m in text for m in CABLE_MISSING)
        if args.status_only:
            if (not missing) and rc == 0:
                for line in text.splitlines():
                    if "configure situation" in line or "Device" in line:
                        print("  " + line.strip())
                print("CHAIN ok (attempt %d, no reconfiguration)" % attempt)
                return 0
        elif rc == 0 and "PROGRAM FLOW DONE" in text and not missing:
            for line in text.splitlines():
                if "Program" in line or "done bit" in line:
                    print("  " + line.strip())
            print("PROGRAMMED ok (attempt %d)" % attempt)
            return 0
        reason = "cable missing" if missing else "tool error (rc=%d)" % rc
        print("attempt %d/%d failed: %s" % (attempt, attempts, reason))
        if attempt == attempts:
            print(text[-800:])
            break
        time.sleep(3.0)
        ensure_jtagserver()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
