"""dwell_test.py — 受控对照：走桥接做 8 轮，烧完等 3s、每轮读 15s，
检验之前短窗口 FAIL 是否只是"烧录后过早开串口"的误判。
"""
from __future__ import annotations

import json
import time
import httpx

API = "http://127.0.0.1:8600"
BEACON = "test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"


def main():
    results = []
    for rnd in range(1, 9):
        box = None
        try:
            httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            r = httpx.post(f"{API}/api/v1/devices/reserve", json={"minutes": 10}, timeout=90).json()
            box = r["box_id"]
            with open(BEACON, "rb") as f:
                b = httpx.post(f"{API}/api/v1/bitstream",
                               files={"file": (BEACON.split("/")[-1], f)}, timeout=600).json()
            print(f"[{rnd}] box={box} ({r['device_name']}) burn={b['programming']} wait3s", flush=True)
            time.sleep(3.0)
            from websockets.sync.client import connect
            got = 0
            first_hex = None
            with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
                deadline = time.time() + 15
                while time.time() < deadline and got < 5:
                    try:
                        m = json.loads(ws.recv(timeout=5))
                    except Exception:
                        continue
                    if m.get("type") == "rx":
                        got += 1
                        if first_hex is None:
                            first_hex = (m.get("hex") or "")[:40]
                    elif m.get("type") == "status" and m.get("state") == "error":
                        print(f"[{rnd}] serial error: {m.get('reason')}")
                        break
            verdict = "PASS" if got else "FAIL"
            results.append((box, verdict, got, first_hex))
            print(f"[{rnd}] box={box} -> {verdict} rx={got} first={first_hex}", flush=True)
        except Exception as e:
            results.append((box, "ERR", 0, str(e)[:80]))
            print(f"[{rnd}] exception: {e}", flush=True)
        finally:
            try:
                httpx.post(f"{API}/api/v1/devices/release", timeout=60)
            except Exception:
                pass
    print("\nSUMMARY")
    for box, v, got, fh in results:
        print(f"  box={box} {v} rx={got} {fh or ''}")


if __name__ == "__main__":
    main()
