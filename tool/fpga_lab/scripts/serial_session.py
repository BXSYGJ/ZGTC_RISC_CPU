"""serial_session.py — 保证远程串口可用的标准入口。

背景（2026-09-07 实测）：远程实验箱的串口 RX 有时不送达（时变），与箱子非严格绑定
（实验箱4 某次 FAIL、重约后 PASS）。可靠做法是"信标门"：先烧 uart_beacon 验证 ≥N 次 rx，
通过才保留该会话；失败即释放并重约，直到拿到健康会话，再烧用户固件并开串口。

用法（bridge server 需在 127.0.0.1:8600 运行）：
  python serial_session.py --firmware path/to/user.sbit [--tx-hex A5] [--seconds 8]
  # 不烧用户固件、仅找健康箱： python serial_session.py --beacon-only

行为：release -> (reserve -> burn beacon -> read) 重试至通过 -> 烧 firmware -> 串口收 N 秒
       -> release（异常也在 finally 释放）。输出每步与最终 rx 摘要。
"""
from __future__ import annotations

import argparse
import json
import time
import httpx

API = "http://127.0.0.1:8600"
BEACON = "test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
REQUIRED_RX = 2          # 信标需至少收到几次 rx 事件才判通
READ_AFTER_FINAL_S = 8   # 烧完用户固件后串口读取时长


def bridge(method, path, **kw) -> dict:
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"bridge {method} {path}: {r.status_code} {j}")
    return j


def _burn(sbit_path: str) -> dict:
    with open(sbit_path, "rb") as f:
        return bridge("POST", "/api/v1/bitstream",
                      files={"file": (sbit_path.split("/")[-1], f)}, timeout=600)


def _serial_read(seconds: float, tx_payload: tuple | None = None) -> list[dict]:
    from websockets.sync.client import connect
    rx = []
    with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
        sent = False
        deadline = time.time() + seconds + 8
        while time.time() < deadline:
            try:
                m = json.loads(ws.recv(timeout=5))
            except Exception:
                continue
            t = m.get("type")
            if t == "status" and m.get("state") == "connected" and tx_payload and not sent:
                mode, data = tx_payload
                ws.send(json.dumps({"type": "tx", "mode": mode, "data": data}))
                sent = True
            elif t == "ack":
                pass
            elif t == "rx":
                rx.append({"hex": m.get("hex"), "text": m.get("data_text")})
            elif t == "error":
                raise RuntimeError(f"serial error: {m.get('reason')}")
    return rx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=None, help="user .sbit to burn after healthy box found")
    ap.add_argument("--tx-hex", default=None)
    ap.add_argument("--tx-text", default=None)
    ap.add_argument("--seconds", type=float, default=READ_AFTER_FINAL_S)
    ap.add_argument("--attempts", type=int, default=6)
    ap.add_argument("--keep", action="store_true", help="leave box reserved (do not release at end)")
    ap.add_argument("--beacon-only", action="store_true", help="only find+keep a healthy box (no user firmware)")
    args = ap.parse_args()

    box = None
    try:
        # release any current, then hunt for a healthy serial session
        healthy = False
        for attempt in range(1, args.attempts + 1):
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print(f"[{attempt}] box {box} ({r['device_name']}) reserved; beacon burn...", flush=True)
            _burn(BEACON)
            rx = _serial_read(5.0)
            print(f"[{attempt}] beacon rx events={len(rx)}", flush=True)
            if len(rx) >= REQUIRED_RX:
                healthy = True
                print(f"  -> serial healthy on box {box}", flush=True)
                break
            print(f"  -> serial NOT delivered on box {box}; release & re-reserve", flush=True)
        if not healthy:
            print("ERROR: no serial-healthy session found in attempts")
            return 1

        if args.beacon_only:
            print(f"OK: box {box} reserved & beacon running. Use --firmware to load your design.")
            return 0

        if not args.firmware:
            print("provide --firmware (or --beacon-only) to proceed")
            return 1

        print(f"burn user firmware {args.firmware} ...", flush=True)
        b = _burn(args.firmware)
        print(f"  burn state={b['programming']} detail={b['detail']}")

        tx = None
        if args.tx_hex:
            tx = ("hex", args.tx_hex)
        elif args.tx_text:
            tx = ("text", args.tx_text)
        rx = _serial_read(args.seconds, tx)
        print(f"\nRESULT: box={box} firmware={args.firmware} rx_events={len(rx)}")
        for m in rx[:6]:
            print(f"  rx hex={m['hex']} text={m['text']!r}")
        return 0 if rx else 2
    finally:
        if not args.keep:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
                print("[release] ok")
            except Exception as e:
                print("[!] release failed", e)


if __name__ == "__main__":
    raise SystemExit(main())
