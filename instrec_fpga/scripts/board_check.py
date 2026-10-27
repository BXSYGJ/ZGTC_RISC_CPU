#!/usr/bin/env python3
"""One-shot board check: FTDI present -> program -> read status -> capture UART.

The script automates the sequence that was previously done by hand:
  1. confirm the FTDI downloader (VID_0403) is present;
  2. start jtagserver and wait for 127.0.0.1:65420;
  3. open the UART *before* programming so the boot banner is not missed;
  4. program the given .sbit and wait for "PROGRAM FLOW DONE";
  5. scan the chain and read the device status register (mode 3);
  6. capture N seconds of UART and print a compact report.

Usage:
  python scripts/board_check.py --sbit build/instrec-latest.sbit --port COM5 --seconds 12
  python scripts/board_check.py --sbit releases/m1-20261027/instrec_top.sbit --status-only

Exit codes: 0 ok, 2 no downloader / port, 3 program failed.
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


def kill_tools():
    run_ps('Get-Process cdt_js,cdt_cfg -ErrorAction SilentlyContinue | Stop-Process -Force')


def ftdi_present():
    out = run_ps("(Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_0403' } | Measure-Object).Count")
    try:
        return int(out.stdout.strip().splitlines()[-1]) > 0
    except Exception:
        return False


def start_server(timeout=15.0):
    proc = subprocess.Popen([str(PDS / 'cdt_js.exe'), '-port', '65420'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', 65420), timeout=0.5):
                return proc
        except OSError:
            time.sleep(0.5)
    return None


def run_tcl(name, body, timeout=90):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tcl = LOG_DIR / f'board_check_{name}.tcl'
    log = LOG_DIR / f'board_check_{name}.log'
    tcl.write_text(body, encoding='utf-8', newline='\n')
    with open(log, 'w') as fh:
        proc = subprocess.Popen([str(PDS / 'cdt_cfg.exe'), '-file', str(tcl)],
                                stdout=fh, stderr=subprocess.STDOUT)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1)
        text = log.read_text(errors='replace')
        if 'PROGRAM FLOW DONE' in text or 'STATUS DONE' in text:
            break
    proc.terminate()
    return log.read_text(errors='replace')


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
    ap.add_argument('--freq', default='10Mhz')
    args = ap.parse_args()

    if not ftdi_present():
        print('FTDI downloader (VID_0403) is not present; re-plug USB Cable II.')
        return 2

    if not args.status_only and not args.sbit:
        print('--sbit is required unless --status-only is used')
        return 2

    sbit = str((ROOT / args.sbit).resolve()) if args.sbit else None
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

    kill_tools()
    time.sleep(2)
    js = start_server()
    if js is None:
        print('jtagserver did not open port 65420')
        return 2

    try:
        text = run_tcl('program', status_body(sbit, args.freq) if sbit else status_body(None, args.freq))
        done = parse_done(text)
        print(f'program: {"PROGRAM FLOW DONE" in text}')
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
        if js is not None:
            js.terminate()
        kill_tools()

    raw = b''.join(chunks)
    if raw:
        print(f'uart: {len(raw)} bytes')
        print(raw[:200].decode('ascii', 'replace'))
    else:
        print('uart: 0 bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())