#!/usr/bin/env python3
"""WMWL USB switch control: power-cycle the JTAG downloader without a replug.

The USB Cable II (FT2232, VID_0403&PID_6010) wedges at the USB level every few
hours -- PnP shows it as Unknown and cdt_cfg reports "No PANGO USB CABLE II
cable was found in system".  Until now the only cure was a physical replug.

This controller sits inline on the downloader's USB power and takes 4-byte
commands at 9600 8-N-1 (last byte = sum of the first three, mod 256):

    A0 01 00 A1   relay off  (downstream USB power cut)
    A0 01 01 A2   relay on   (power restored)
    A0 01 05 A6   status     -> A0 01 <00|01> <sum>

The controller enumerates as a CH340 (VID_1A86&PID_7523) and is NOT the board
UART (CP210x, VID_10C4), so the port is resolved by VID unless --port is given.

Usage
-----
    python scripts/usb_switch.py status
    python scripts/usb_switch.py cycle              # off 0.8 s, on, wait for PnP OK
    python scripts/usb_switch.py recover            # cycle + wait for the downloader
    python scripts/usb_switch.py off|on

Exit codes: 0 ok, 1 the switch did not answer, 2 the downloader never came back.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

BAUD = 9600
RELAY = 0x01
CMD_OFF = bytes([0xA0, RELAY, 0x00])
CMD_ON = bytes([0xA0, RELAY, 0x01])
CMD_STATUS = bytes([0xA0, RELAY, 0x05])

SWITCH_VID = "1A86"          # CH340 on the WMWL controller
BOARD_UART_VID = "10C4"      # CP210x: the board console, never the switch
JTAG_VID_PID = "VID_0403&PID_6010"   # USB Cable II (FT2232)


def _sum3(cmd: bytes) -> bytes:
    return bytes(list(cmd) + [sum(cmd) & 0xFF])


def find_switch_port(explicit: str | None = None) -> str:
    """Resolve the CH340 behind the switch, ignoring the board UART."""
    if explicit:
        return explicit
    from serial.tools import list_ports

    hits = [p.device for p in list_ports.comports()
            if SWITCH_VID in (p.hwid or "").upper()]
    hits = [h for h in hits if BOARD_UART_VID not in
            next((p.hwid or "" for p in list_ports.comports() if p.device == h), "").upper()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit("no CH340 found: is the USB switch plugged in?")
    raise SystemExit("several CH340 ports (%s); pass --port" % ", ".join(hits))


def _open(port: str):
    import serial
    return serial.Serial(port, BAUD, timeout=0.5)


def send(port: str, cmd: bytes, expect_reply: bool = False) -> bytes:
    ser = _open(port)
    try:
        ser.reset_input_buffer()
        ser.write(_sum3(cmd))
        if not expect_reply:
            time.sleep(0.15)
            return b""
        time.sleep(0.2)
        return ser.read(8)
    finally:
        ser.close()


def status(port: str | None = None) -> str:
    p = find_switch_port(port)
    reply = send(p, CMD_STATUS, expect_reply=True)
    if len(reply) < 3 or reply[0] != 0xA0:
        raise SystemExit("switch on %s did not answer (got %r)" % (p, reply))
    return "ON" if reply[2] == 0x01 else "OFF"


def jtag_device_state() -> str:
    """Return the PnP status of the USB Cable II ("OK", "Unknown", "absent")."""
    ps = ("Get-PnpDevice | Where-Object { $_.InstanceId -like '*%s*' } | "
          "Select-Object -ExpandProperty Status") % JTAG_VID_PID
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True)
    text = (out.stdout or "").strip()
    if not text:
        return "absent"
    states = [s.strip() for s in text.splitlines() if s.strip()]
    if all(s == "OK" for s in states):
        return "OK"
    return states[0]


def cycle(port: str | None = None, off_seconds: float = 0.8) -> str:
    p = find_switch_port(port)
    send(p, CMD_OFF)
    time.sleep(off_seconds)
    send(p, CMD_ON)
    time.sleep(0.3)
    return p


def recover(port: str | None = None, timeout: float = 30.0,
            off_seconds: float = 0.8) -> bool:
    """Power-cycle the downloader and wait until PnP reports it healthy again."""
    p = cycle(port, off_seconds)
    print("power-cycled the downloader via %s" % p)
    deadline = time.time() + timeout
    seen = None
    while time.time() < deadline:
        st = jtag_device_state()
        if st != seen:
            print("  USB Cable II: %s" % st)
            seen = st
        if st == "OK":
            return True
        time.sleep(1.0)
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("status", "off", "on", "cycle", "recover"))
    ap.add_argument("--port", default=None, help="switch COM port (default: CH340)")
    ap.add_argument("--off-seconds", type=float, default=0.8)
    ap.add_argument("--timeout", type=float, default=30.0)
    args = ap.parse_args(argv)

    if args.action == "status":
        print(status(args.port))
    elif args.action == "off":
        send(find_switch_port(args.port), CMD_OFF)
        print("relay OFF")
    elif args.action == "on":
        send(find_switch_port(args.port), CMD_ON)
        print("relay ON")
    elif args.action == "cycle":
        print("power-cycled the downloader via %s" % cycle(args.port, args.off_seconds))
    else:
        return 0 if recover(args.port, args.timeout, args.off_seconds) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
