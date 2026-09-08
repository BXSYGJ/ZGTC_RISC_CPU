"""targeted_serial_check.py — 反复预约直到命中目标箱子，再烧 uart_beacon 验证串口。

目标默认 id {14, 59, 61}：实验箱4 / 实验箱9 / gateway 192.168.2.31（用户报告可疑箱）。
用法：python targeted_serial_check.py [--targets 14 61 59] [--max-rounds 40]
"""
from __future__ import annotations

import argparse
import json
import time
import httpx

API = "http://127.0.0.1:8600"
SBIT = "test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="+", type=int, default=[14, 59, 61])
    ap.add_argument("--max-rounds", type=int, default=40)
    ap.add_argument("--seconds", type=float, default=6.0)
    args = ap.parse_args()
    from websockets.sync.client import connect

    results = {}       # box_id -> "PASS"/"FAIL"
    seen = {}
    tested = set()
    for rnd in range(1, args.max_rounds + 1):
        try:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            r = httpx.post(f"{API}/api/v1/devices/reserve", json={"minutes": 10}, timeout=90).json()
        except Exception as e:
            print(f"round {rnd}: bridge error {e}"); break
        box = r["box_id"]
        name = r["device_name"]
        seen.setdefault(box, name)
        if box in tested:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            continue
        print(f"round {rnd}: got box {box} ({name})")
        if box not in args.targets:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            if rnd % 8 == 0:
                print(f"  ... tried {len(seen)} distinct boxes so far: "
                      f"{[(k,v) for k,v in seen.items()]}")
            continue

        # burn beacon + read
        with open(SBIT, "rb") as f:
            b = httpx.post(f"{API}/api/v1/bitstream",
                           files={"file": (SBIT.split("/")[-1], f)}, timeout=600).json()
        print(f"  burn state={b['programming']}")
        got = []
        diag = 0
        try:
            with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
                deadline = time.time() + args.seconds + 8
                while time.time() < deadline and len(got) < 8:
                    try:
                        m = json.loads(ws.recv(timeout=5))
                    except Exception:
                        continue
                    if m.get("type") == "rx":
                        got.append(m.get("hex"))
                        print(f"  [rx] {m.get('hex')[:40]}...")
                    elif m.get("type") == "diagnostic":
                        diag += 1
                        if diag <= 2:
                            print("  [diag]", (m.get("message") or "")[:90])
                    elif m.get("type") == "status" and m.get("state") == "error":
                        print("  [error]", m.get("reason")); break
        except Exception as e:
            print("  ws error", e)
        verdict = "PASS" if got else "FAIL"
        results[box] = verdict
        tested.add(box)
        print(f"  => box {box} ({name}) {verdict}  (rx={len(got)} diag={diag})")
        if len(results) >= len(args.targets):
            break
        try:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
        except Exception:
            pass

    print("\n===== SUMMARY =====")
    for box, name in seen.items():
        print(f"  box {box} ({name}): {results.get(box, 'not-tested-this-run')}")
    return 0 if all(v == "PASS" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
