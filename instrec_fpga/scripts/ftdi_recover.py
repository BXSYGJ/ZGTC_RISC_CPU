"""Recover a FTDI downloader that has vanished from PnP (CM_PROB_PHANTOM).

Background (board_check.py header, rule R2): killing a cdt_cfg while its
D2XX handle is open leaves the FT2232H in a bus-hung state; Windows then
reports it as CM_PROB_PHANTOM and unplug/re-plug was the only fix we knew.
The present script tries three software-only recoveries before giving up:

  1. if a zombie cdt_js is holding no device any more (port closed AND
     VID_0403 count == 0), kill it first -- it has nothing to lose;
  2. ``pnputil /scan-devices`` (or ``devcon rescan`` as a fallback) to
     force a full PnP re-enumeration;
  3. ``devcon restart`` on every USB Root Hub / Host Controller -- the
     nuclear option, but still software-only and way cheaper than a cable.

After each step the VID_0403 count is polled for ``--wait`` seconds; the
first non-zero count wins.  ``--dry-run`` prints what would happen and
stops before killing anything.

This script is deliberately OUTSIDE the hard "never kill cdt_js" rule of
board_check.py -- that rule is there to protect a LIVE downloader that
still holds its D2XX handle; this script only acts when the handle has
already been lost for good, i.e. when VID_0403 is zero.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import re
import subprocess
import sys
import time


def run_ps(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', cmd],
        capture_output=True, text=True, timeout=timeout)


def ftdi_count() -> int:
    out = run_ps(
        "(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue "
        "| Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count")
    try:
        return int(out.stdout.strip().splitlines()[-1])
    except Exception:
        return 0


def cdt_js_pids() -> list[int]:
    out = run_ps("Get-Process cdt_js -ErrorAction SilentlyContinue "
                 "| ForEach-Object { $_.Id }")
    pids: list[int] = []
    for line in out.stdout.splitlines():
        line = line.strip().lstrip('\ufeff')
        if line.isdigit():
            pids.append(int(line))
    return pids


def cdt_js_port_open() -> bool:
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 65420), timeout=0.5):
            return True
    except OSError:
        return False


def has_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def wait_for_ftdi(wait: float, label: str) -> bool:
    deadline = time.time() + wait
    while time.time() < deadline:
        n = ftdi_count()
        if n > 0:
            print(f'  [OK]  VID_0403 count = {n} after {label}')
            return True
        time.sleep(1.0)
    n = ftdi_count()
    print(f'  [--]  VID_0403 count = {n} after {label} ({wait:.0f}s waited)')
    return n > 0


def kill_zombie_cdt_js() -> bool:
    """Kill cdt_js only if its port is closed AND FTDI is already gone.

    A live cdt_js that still holds its D2XX handle must never be touched --
    that is the exact mistake that caused the original phantom behaviour.
    """
    pids = cdt_js_pids()
    if not pids:
        print('  cdt_js not running; nothing to kill.')
        return True

    port_open = cdt_js_port_open()
    ftdi = ftdi_count()

    if port_open and ftdi > 0:
        print(f'  cdt_js port OPEN ({pids}) AND FTDI present (count={ftdi}); '
              f'NOT killing -- live session.')
        return False

    if port_open and ftdi == 0:
        print(f'  cdt_js port OPEN ({pids}) but FTDI count=0 -- unusual, '
              f'skipping kill (port may reopen).')
        return False

    print(f'  cdt_js port CLOSED, FTDI count=0 -> zombie safe to kill '
          f'(pids={pids}).')
    run_ps('Stop-Process -Id ' + ','.join(str(p) for p in pids)
           + ' -Force -ErrorAction SilentlyContinue')
    time.sleep(1.0)
    pids2 = cdt_js_pids()
    if pids2:
        print(f'  !! some cdt_js still alive: {pids2}')
        return False
    print('  cdt_js terminated.')
    return True


def pnputil_scan() -> bool:
    """``pnputil /scan-devices`` refreshes the whole device tree."""
    print('  pnputil /scan-devices ...')
    r = subprocess.run(['pnputil', '/scan-devices'],
                       capture_output=True, text=True, timeout=30)
    out = (r.stdout or '') + (r.stderr or '')
    ok = ('Scan complete' in out) or ('完成' in out)
    print(f'  pnputil exit={r.returncode} scan_complete={ok}')
    return ok


def devcon_rescan() -> bool:
    r = subprocess.run(['devcon', 'rescan'],
                       capture_output=True, text=True, timeout=30)
    print(f'  devcon rescan exit={r.returncode}: '
          f'{(r.stdout or "").strip()[:200]}')
    return r.returncode == 0


def devcon_restart_usb() -> bool:
    """Restart every USB Root Hub and Host Controller (admin required).

    This is the nuclear option: it drops *every* USB device momentarily,
    not just the FTDI dongle.  CP2102 (COM5) will also cycle, but the board
    keeps running so we only lose a few log lines.
    """
    pattern = r'(USBROOT|USBHUB|pci\\VEN_.*U[SH][BH])'
    out = run_ps(
        "Get-PnpDevice -Class USB -ErrorAction SilentlyContinue "
        "| Where-Object { $_.InstanceId -match 'USBROOT|USBHUB|U[SH]B' } "
        "| ForEach-Object { $_.InstanceId }")
    ids = [x.strip() for x in out.stdout.splitlines()
           if x.strip() and re.search(pattern, x.strip(), re.I)]
    if not ids:
        print('  no USB Root Hub / Host Controller instances found.')
        return False
    print(f'  will restart {len(ids)} USB devices:')
    for i in ids:
        print(f'    - {i}')
    any_ok = False
    for i in ids:
        r = subprocess.run(['devcon', 'restart', i],
                           capture_output=True, text=True, timeout=20)
        rc = r.returncode
        if rc == 0:
            any_ok = True
            print(f'    restart OK  : {i}')
        else:
            print(f'    restart {rc}: {i} '
                  f'{(r.stdout or "").strip()[:120]}')
        time.sleep(1.0)
    return any_ok


def start_cdt_js() -> int | None:
    pds_root = os.environ.get('PDS_ROOT', r'H:\GG\pango\PDS_2022.2-SP6.4')
    exe = os.path.join(pds_root, 'bin', 'cdt_js.exe')
    if not os.path.exists(exe):
        print(f'  cdt_js not found at {exe}')
        return None
    import socket
    try:
        with socket.create_connection(('127.0.0.1', 65420), timeout=0.5):
            print('  port 65420 already listening, cdt_js already up.')
            return None
    except OSError:
        pass
    flags = 0
    if hasattr(subprocess, 'DETACHED_PROCESS'):
        flags = subprocess.DETACHED_PROCESS
    proc = subprocess.Popen(
        [exe, '-port', '65420'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, close_fds=True)
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', 65420), timeout=0.5):
                print(f'  cdt_js PID={proc.pid} listening on :65420')
                return proc.pid
        except OSError:
            time.sleep(0.5)
    print(f'  cdt_js PID={proc.pid} did not open port 65420 in time.')
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--wait', type=float, default=15.0,
                    help='seconds to poll VID_0403 after each step')
    ap.add_argument('--skip-restart-usb', action='store_true',
                    help='do NOT restart USB root hubs (nuclear option)')
    ap.add_argument('--dry-run', action='store_true',
                    help='print what would happen, do not kill or restart anything')
    args = ap.parse_args()

    print(f'initial state:  VID_0403 count={ftdi_count()}, '
          f'cdt_js pids={cdt_js_pids()}, port_open={cdt_js_port_open()}, '
          f'admin={has_admin()}')

    if ftdi_count() > 0:
        print('FTDI already present -- nothing to recover.')
        return 0

    # --- step 1: kill zombie cdt_js ---------------------------------------------------
    print('\n[1/4] kill zombie cdt_js')
    if args.dry_run:
        print('  (dry-run, would call kill_zombie_cdt_js)')
    else:
        kill_zombie_cdt_js()

    # --- step 2: pnputil /scan-devices -----------------------------------------------
    print('\n[2/4] pnputil /scan-devices')
    if args.dry_run:
        print('  (dry-run)')
    else:
        pnputil_scan()
    if wait_for_ftdi(args.wait, 'pnputil /scan-devices'):
        print('\n== RECOVERED after step 2 ==')
        if not args.dry_run:
            start_cdt_js()
        return 0

    # --- step 3: devcon rescan (fallback) ---------------------------------------------
    print('\n[3/4] devcon rescan')
    if args.dry_run:
        print('  (dry-run)')
    else:
        if not devcon_rescan():
            print('  devcon not available, skipping step 3.')
        else:
            if wait_for_ftdi(args.wait, 'devcon rescan'):
                print('\n== RECOVERED after step 3 ==')
                if not args.dry_run:
                    start_cdt_js()
                return 0
    # --- step 4: restart USB root hubs (nuclear) -------------------------------------
    if not args.skip_restart_usb:
        print('\n[4/4] devcon restart USB Root Hubs / Host Controllers')
        if not has_admin():
            print('  !! this step requires Administrator elevation; re-run from '
                  'an elevated PowerShell if you want to try it.')
        elif args.dry_run:
            print('  (dry-run)')
        else:
            devcon_restart_usb()
            if wait_for_ftdi(args.wait, 'USB hub restart'):
                print('\n== RECOVERED after step 4 ==')
                start_cdt_js()
                return 0

    print('\n** None of the software recoveries worked.**')
    print('   The FT2232H is in CM_PROB_PHANTOM state and the only known fix '
          'is a physical re-plug of the USB Cable II.')
    print('   Once the cable is re-plugged, run me again (or `board_check.py`) '
          'and I will find it immediately.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
