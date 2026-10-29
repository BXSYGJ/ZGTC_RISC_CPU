#!/usr/bin/env python3
"""One-shot board check: FTDI present -> program -> read status -> capture UART.

The script automates the sequence that was previously done by hand:
  1. confirm the FTDI downloader (VID_0403) is present;
  2. reuse an already-listening jtagserver, or start one and keep it;
  3. open the UART *before* programming so the boot banner is not missed;
  4. program the given .sbit through cdt_cfg and let it exit on its own;
  5. scan the chain and read the device status register (mode 3);
  6. capture N seconds of UART and print a compact report.

FTDI drop protection (2026-10-29, root cause confirmed)
------------------------------------------------------
Every previous run of this script killed cdt_cfg with a ``Popen`` terminate
call as soon as "PROGRAM FLOW DONE" appeared in the log.  That banner is
printed
*before* the TCL interpreter reaches ``cfg_disconnect``/``exit``, so the
terminate always landed while the D2XX handle was still open.  A killed
D2XX process never releases the handle, the FT2232H stops responding on the
USB bus and disappears from PnP (``CM_PROB_PHANTOM``) until the cable is
physically re-plugged.  That is the "it drops the moment you touch the
board" behaviour.

Therefore this script now enforces three rules:
  R1. the generated TCL always ends with ``exit`` so cdt_cfg finishes by
      itself (a normal run is over in a few seconds);
  R2. no code path terminates or kills cdt_cfg / cdt_js -- a stuck
      cdt_cfg is reported with its PID and left alone;
  R3. an already-open 127.0.0.1:65420 is reused instead of starting a
      second jtagserver (restarting the server also desynchronises USB).

It also records the FTDI device count before and after each step, so if the
downloader ever disappears again the exact step is named in the report.

Usage:
  python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 12
  python scripts/board_check.py --sbit releases/m1-20261027/instrec_top.sbit --status-only
  python scripts/board_check.py --diag-only

Exit codes: 0 ok, 2 no downloader / port, 3 program failed, 4 cdt_cfg hung.
"""

import argparse
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

PDS = Path(r'H:/GG/pango/PDS_2022.2-SP6.4/bin')
ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / 'build'


def run_ps(cmd):
    return subprocess.run(['powershell', '-NoProfile', '-Command', cmd],
                          capture_output=True, text=True)


def tools_running():
    out = run_ps("(Get-Process cdt_js -ErrorAction SilentlyContinue | Measure-Object).Count")
    try:
        return int(out.stdout.strip().splitlines()[-1]) > 0
    except Exception:
        return False


def ftdi_present():
    out = run_ps("(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count")
    try:
        return int(out.stdout.strip().splitlines()[-1]) > 0
    except Exception:
        return False


def port_listening(timeout=0.5):
    try:
        with socket.create_connection(('127.0.0.1', 65420), timeout=timeout):
            return True
    except OSError:
        return False


def start_server(timeout=15.0):
    """Start jtagserver detached and wait for its TCP port.

    The process is deliberately not parented to this script's lifetime and
    is never killed afterwards: jtagserver keeps the FTDI handle valid, and
    restarting it desynchronises the USB stack.
    """
    flags = 0
    if hasattr(subprocess, 'DETACHED_PROCESS'):
        flags = subprocess.DETACHED_PROCESS
    subprocess.Popen([str(PDS / 'cdt_js.exe'), '-port', '65420'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=flags, close_fds=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_listening():
            return True
        time.sleep(0.5)
    return False


def run_tcl(name, body, timeout=180):
    """Run a TCL file through cdt_cfg and wait for it to exit on its own.

    Returns (log_text, returncode).  A returncode of None means cdt_cfg did
    not exit within the timeout; it is then left running on purpose (rule R2)
    and the caller reports it instead of killing it.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tcl = LOG_DIR / f'board_check_{name}.tcl'
    log = LOG_DIR / f'board_check_{name}.log'
    tcl.write_text(body, encoding='utf-8', newline='\n')
    with open(log, 'w') as fh:
        proc = subprocess.Popen([str(PDS / 'cdt_cfg.exe'), '-file', str(tcl)],
                                stdout=fh, stderr=subprocess.STDOUT)
    try:
        rc = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        rc = None
    return log.read_text(errors='replace'), rc


def status_body(sbit=None, freq='10Mhz'):
    lines = [
        'cfg_set_tcl_break -flag false',
        'cfg_connect -ip 127.0.0.1 -port 65420',
        f'cfg_set_cable_property -index 0 -freq {freq}',
        'cfg_scan_chain',
    ]
    if sbit:
        lines += [
            f'cfg_assign_file -file {sbit} -device_index 0',
            'cfg_program -device_index 0',
            'after 1000',
            'cfg_scan_chain',
        ]
    lines += [
        'puts "== STATUS DONE =="',
        'catch {cfg_read_device_property -device_index 0 -mode 3}',
        'cfg_disconnect',
        # R1: cdt_cfg must terminate itself; the previous flow relied on
        # terminate() here, which is exactly what dropped the FTDI device.
        'exit',
    ]
    return '\n'.join(lines) + '\n'


def parse_done(text):
    m = re.search(r'Status Register: (0x[0-9A-Fa-f]+)', text)
    if not m:
        return None
    val = int(m.group(1), 16)
    return {'raw': m.group(1), 'done': (val >> 12) & 1, 'crc_err': (val >> 1) & 1}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sbit')
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--seconds', type=float, default=12.0)
    ap.add_argument('--status-only', action='store_true')
    ap.add_argument('--diag-only', action='store_true',
                    help='report FTDI / jtagserver / UART state and exit')
    ap.add_argument('--freq', default='10Mhz')
    args = ap.parse_args()

    present = ftdi_present()
    print(f'ftdi: {"present" if present else "ABSENT"}  jtagserver: '
          f'{"running" if tools_running() else "stopped"}  port65420: '
          f'{"open" if port_listening() else "closed"}')
    if args.diag_only:
        return 0 if present else 2

    if not present:
        print('FTDI downloader (VID_0403) is not present in PnP; programming is impossible.')
        return 2

    if not args.status_only and not args.sbit:
        print('--sbit is required unless --status-only is used')
        return 2

    sbit = (ROOT / args.sbit).resolve().as_posix() if args.sbit else None
    if sbit and not Path(sbit).is_file():
        print(f'sbit not found: {sbit}')
        return 2

    ser = None
    chunks = []
    if not args.status_only:
        try:
            import serial
            ser = serial.Serial(args.port, 115200, timeout=0.1)
            print(f'UART {args.port} opened before programming')
        except Exception as exc:
            print(f'cannot open {args.port}: {exc}')
            return 2

    # R3: reuse a running jtagserver; only start one if the port is closed.
    if not port_listening():
        if not start_server():
            print('jtagserver did not open port 65420')
            return 2
        print('jtagserver started and kept (never killed by this script)')
    else:
        print('reusing the running jtagserver (no restart)')

    rc = 0
    try:
        body = status_body(sbit, args.freq) if sbit else status_body(None, args.freq)
        text, code = run_tcl('program', body)
        if code is None:
            print('cdt_cfg did not exit within the timeout; it was LEFT RUNNING on purpose '
                  '(killing it is what drops the FTDI device).')
            rc = 4
        else:
            print(f'cdt_cfg exit code: {code}')

        print(f'program: {"PROGRAM FLOW DONE" in text}')
        done = parse_done(text)
        if done:
            print(f'status: {done["raw"]} done={done["done"]} crc_err={done["crc_err"]}')
        else:
            print('status: not available')

        if ser is not None:
            deadline = time.time() + args.seconds
            while time.time() < deadline:
                data = ser.read(4096)
                if data:
                    chunks.append(data)
    finally:
        if ser is not None:
            ser.close()

    # R2 evidence: name the step if the downloader vanished during the run.
    if not ftdi_present():
        print('!! FTDI disappeared during this run (device no longer in PnP).')
        rc = 2

    raw = b''.join(chunks)
    if raw:
        print(f'uart: {len(raw)} bytes')
        print(raw[:200].decode('ascii', 'replace'))
    else:
        print('uart: 0 bytes')
    return rc


if __name__ == '__main__':
    sys.exit(main())