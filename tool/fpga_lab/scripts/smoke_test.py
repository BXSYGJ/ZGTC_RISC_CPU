"""smoke_test.py — live verification of the fpga-lab bridge on the real platform.

Order (release always runs):
  reserve -> burn <sbit> -> serial open/send/read -> release
Requires the bridge server on http://127.0.0.1:8600.
Usage: python smoke_test.py [--sbit path/to/file.sbit] [--serial-hex A5] [--serial-text help]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

API = "http://127.0.0.1:8600"


def jget(resp: httpx.Response):
    j = resp.json()
    if resp.status_code >= 400:
        raise SystemExit(f"bridge error {resp.status_code}: {j}")
    return j


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sbit", default="pds_soc_top.sbit")
    ap.add_argument("--minutes", type=int, default=10)
    ap.add_argument("--serial-hex", default="A5")
    ap.add_argument("--serial-text", default=None)
    ap.add_argument("--wait", type=float, default=6.0)
    args = ap.parse_args()

    from websockets.sync.client import connect

    try:
        h = httpx.get(f"{API}/api/v1/health", timeout=15).json()
        assert h["session"]["authenticated"], "bridge not authenticated"
        print("[1] health ok", h["session"])

        # release anything left over, then reserve
        httpx.post(f"{API}/api/v1/devices/release", timeout=60)
        r = jget(httpx.post(f"{API}/api/v1/devices/reserve", json={"minutes": args.minutes}, timeout=90))
        print(f"[2] reserved {r['device_name']} box_id={r['box_id']} until {r['reserved_until']}")

        with open(args.sbit, "rb") as f:
            b = jget(httpx.post(f"{API}/api/v1/bitstream",
                                files={"file": (args.sbit.split("/")[-1], f)}, timeout=600))
        print(f"[3] burn ok sha256={b['sha256']} state={b['programming']} detail={b['detail']}")

        ws_url = f"ws://127.0.0.1:8600/ws/serial?baud=115200"
        rx = []
        with connect(ws_url, open_timeout=20) as ws:
            connected = False
            deadline = time.time() + 30
            while time.time() < deadline:
                m = json.loads(ws.recv(timeout=10))
                t = m.get("type")
                if t == "status" and m.get("state") == "connected":
                    connected = True
                    print(f"[4] serial connected box={m.get('box_id')} config={m.get('config')}")
                    if args.serial_hex:
                        ws.send(json.dumps({"type": "tx", "mode": "hex", "data": args.serial_hex}))
                        print(f"    sent hex {args.serial_hex}")
                    if args.serial_text:
                        ws.send(json.dumps({"type": "tx", "mode": "text", "data": args.serial_text}))
                        print(f"    sent text {args.serial_text!r}")
                    rxdline = time.time() + args.wait
                elif t == "ack":
                    print(f"    ack bytesSent={m.get('bytesSent')}")
                elif t == "rx":
                    rx.append(m)
                    print(f"[rx] hex={m.get('hex')} text={m.get('data_text')!r}")
                    if connected and time.time() > rxdline:
                        break
                elif t == "diagnostic":
                    print(f"[diag] {m.get('message')}")
                if connected and time.time() > rxdline + 3:
                    break
            ws.send(json.dumps({"type": "close"}))
        if not rx:
            print("[!] no rx bytes received over serial")
    finally:
        # ALWAYS release
        try:
            rel = httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            print("[5] release", rel.json())
        except Exception as e:
            print("[!] release failed", e)
            sys.exit(1)


if __name__ == "__main__":
    main()
