"""check_serial.py — 判定当前预约箱子的串口链路是否健康（与固件交互无关）。

原理：烧 uart_beacon.sbit（持续以 115200 8N1 在 AB26 发送字节流），打开串口读 ~N 秒。
  - 收到连续非空字节  -> 串口桥正常（绿）
  - 全程 0x00/allZero  -> 串口桥没收到 FPGA TX（红，可能是该箱路由问题或位流未驻留）

用法（bridge server 需运行）：
  python check_serial.py [--sbit test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit] [--seconds 6]
"""
from __future__ import annotations

import argparse
import json
import time
import httpx

API = "http://127.0.0.1:8600"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sbit", default="test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit")
    ap.add_argument("--minutes", type=int, default=10)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--no-reserve", action="store_true", help="assume a device is already reserved")
    args = ap.parse_args()
    from websockets.sync.client import connect

    box = None
    try:
        if not args.no_reserve:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            r = httpx.post(f"{API}/api/v1/devices/reserve", json={"minutes": args.minutes}, timeout=90).json()
            box = r["box_id"]
            print(f"[reserved] {r['device_name']} box_id={box} until {r['reserved_until']}")

        with open(args.sbit, "rb") as f:
            b = httpx.post(f"{API}/api/v1/bitstream",
                           files={"file": (args.sbit.split("/")[-1], f)}, timeout=600).json()
        print(f"[burn] {b['file_name']} sha256={b['sha256']} state={b['programming']} detail={b['detail']}")

        bytes_seen = []
        zeros = 0
        with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
            deadline = time.time() + args.seconds + 8
            while time.time() < deadline:
                try:
                    m = json.loads(ws.recv(timeout=min(4, deadline - time.time() + 1)))
                except Exception:
                    continue
                t = m.get("type")
                if t == "rx":
                    h = m.get("hex") or ""
                    bytes_seen.append(h)
                    print(f"[rx] {h} text={m.get('data_text')!r}")
                elif t == "diagnostic":
                    zeros += 1
                elif t == "status" and m.get("state") == "error":
                    print(f"[error] {m.get('reason')}")
                    return 3
                if len(bytes_seen) >= 8:
                    break
        if bytes_seen:
            print(f"\nRESULT: PASS  box={box}  (received {len(bytes_seen)} rx events)")
            return 0
        print(f"\nRESULT: FAIL  box={box}  (all-zero/diagnostic x{zeros}; serial bridge received no FPGA TX)")
        return 1
    finally:
        if not args.no_reserve:
            try:
                rel = httpx.post(f"{API}/api/v1/devices/release", timeout=60)
                print("[release]", rel.json())
            except Exception as e:
                print("[!] release failed", e)


if __name__ == "__main__":
    raise SystemExit(main())
