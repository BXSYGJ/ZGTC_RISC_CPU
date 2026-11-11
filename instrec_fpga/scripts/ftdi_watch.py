"""Watchdog: wait for the FTDI downloader, then burn the new counter bitstream
and print the STS phase-2/phase-3 page/done counts.

Run with:
  python scripts/ftdi_watch.py --sbit build/instrec-latest.sbit

Once the user re-plugs the USB Cable II the script:
  1. polls VID_0403 every 3 s until it is present (one single device);
  2. (re)starts ONE cdt_js on port 65420;
  3. invokes board_check.py to flash + read STATUS;
  4. if flash succeeded, captures UART for the STS payload and decodes
     phase-2 (page_cnt) and phase-3 (done_cnt).

This script is deliberately tolerant of being restarted while cdt_js is
already up -- it reuses the existing server instead of spawning another.
"""
from __future__ import annotations

import argparse
import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PDS_ROOT = os.environ.get('PDS_ROOT', r'H:\GG\pango\PDS_2022.2-SP6.4')


def ftdi_count() -> int:
    ps = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue "
         "| Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count"],
        capture_output=True, text=True)
    try:
        return int(ps.stdout.strip().splitlines()[-1])
    except Exception:
        return 0


def cdt_js_pids() -> list[int]:
    ps = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         "Get-Process cdt_js -ErrorAction SilentlyContinue "
         "| ForEach-Object { $_.Id }"],
        capture_output=True, text=True)
    out = []
    for line in ps.stdout.splitlines():
        line = line.strip().lstrip('\ufeff')
        if line.isdigit():
            out.append(int(line))
    return out


def port_open(timeout=0.8) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', 65420), timeout=timeout):
            return True
    except OSError:
        return False


def start_cdt_js() -> bool:
    exe = os.path.join(PDS_ROOT, 'bin', 'cdt_js.exe')
    if not os.path.exists(exe):
        print(f'!! cdt_js not found at {exe}')
        return False
    flags = 0
    if hasattr(subprocess, 'DETACHED_PROCESS'):
        flags = subprocess.DETACHED_PROCESS
    subprocess.Popen([exe, '-port', '65420'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    deadline = time.time() + 25
    while time.time() < deadline:
        if port_open():
            return True
        time.sleep(0.5)
    return False


def ensure_cdt_js() -> bool:
    pids = cdt_js_pids()
    if pids:
        print(f'  cdt_js already running (pids={pids}); waiting for port...')
        deadline = time.time() + 15
        while time.time() < deadline:
            if port_open():
                print('  cdt_js port 65420 listening -> reused.')
                return True
            time.sleep(0.5)
        print(f'  cdt_js alive but port never came up; starting another '
              f'(this should not normally happen)...')
    ok = start_cdt_js()
    if ok:
        print('  cdt_js started and listening.')
    else:
        print('  !! cdt_js failed to start.')
    return ok


def run_board_check(sbit: str, timeout: int = 240) -> tuple[int, str]:
    """Run board_check.py and return (exit_code, stdout_tail)."""
    proc = subprocess.Popen(
        [sys.executable, os.path.join(HERE, 'board_check.py'),
         '--sbit', sbit, '--port', 'COM5', '--seconds', '15'],
        cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out = 'TIMEOUT'
        return -1, out
    return proc.returncode, out


def decode_sts_phases(text: str) -> list[tuple[int, str]]:
    """Extract STS payload hex lines that the CPU firmware prints each phase.

    The CPU firmware in ``sw/rv32/main.c`` prints a single hex token per
    phase rotation, e.g. ``DDR3 STS 00642040``.  Phase 2 carries page_cnt
    (low 18 bit), phase 3 carries done_cnt (low 18 bit).
    """
    vals = re.findall(r'DDR3 STS\s+([0-9A-Fa-f]{8})', text)
    out = []
    for v in vals:
        payload = int(v, 16)
        phase = payload >> 30          # upper 2 bit = win_id[1:0]
        out.append((phase, v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--sbit', required=True)
    ap.add_argument('--once', action='store_true',
                    help='fail immediately if FTDI not present (no polling)')
    ap.add_argument('--interval', type=int, default=3)
    ap.add_argument('--max-wait', type=int, default=1800,
                    help='total seconds to wait (default 30 min)')
    args = ap.parse_args()

    if not os.path.exists(args.sbit):
        print(f'!! bitstream not found: {args.sbit}')
        return 2

    print(f'waiting for FTDI VID_0403 (interval={args.interval}s, '
          f'max={args.max_wait}s)...')
    print(f'bitstream: {args.sbit}')
    start = time.time()
    first_seen = None
    while True:
        n = ftdi_count()
        if n > 0:
            if first_seen is None:
                first_seen = time.time()
                print(f'\n[FTDI DETECTED] VID_0403 count={n} '
                      f'(after {first_seen - start:.0f}s)')
            # give Windows a moment to finish enumeration
            time.sleep(2)
            break
        if args.once:
            print('FTDI not present and --once given; stopping.')
            return 1
        if time.time() - start > args.max_wait:
            print('timeout waiting for FTDI.')
            return 1
        time.sleep(args.interval)
        elapsed = time.time() - start
        if int(elapsed) % 30 == 0 and elapsed > 1:
            print(f'  still waiting ({elapsed:.0f}s)...')

    print('\n--- ensuring cdt_js ---')
    if not ensure_cdt_js():
        return 1

    print('\n--- running board_check.py ---')
    rc, out = run_board_check(args.sbit)
    print(out)
    print(f'\nboard_check exit code = {rc}')

    # Decode STS phases from any captured UART lines.
    phases = decode_sts_phases(out)
    phase_map: dict[int, list[str]] = {}
    for p, v in phases:
        phase_map.setdefault(p, []).append(v)
    print('\n--- STS phase summary ---')
    labels = {0: 'frames/err', 1: 'freeze+mel', 2: 'phase-2 page_cnt (expect 8256)',
              3: 'phase-3 done_cnt (expect 16512)'}
    for p in sorted(labels):
        print(f'  win_id[1:0]={p} ({labels[p]}): '
              f'{phase_map.get(p, ["<no sample>"])}')
    return 0 if rc == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
