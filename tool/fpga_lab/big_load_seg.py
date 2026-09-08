"""Segmented upload: the platform forwards only ~16 KB per serial SESSION to the
board, so large images are split across several serial sessions (close + reopen
between segments). The bootloader's receive is one continuous stream, so it just
keeps receiving across sessions.

Usage: python big_load_seg.py [segment_bytes]
"""
import json
import time
import sys
import httpx
from websockets.sync.client import connect

API = "http://127.0.0.1:8600"
WS = "ws://127.0.0.1:8600/ws/serial?baud=115200"
BEACON = "D:/0000/111/001/Pango/tool/fpga_lab/test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
FIRMWARE = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/pds/20260907-195930-0a2aa5d6/generate_bitstream/pds_soc_top.sbit"
APP = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_big.bin"
SEG = int(sys.argv[1]) if len(sys.argv) > 1 else 15000

state = {"nk": 0}
out = []


def bridge(m, p, **k):
    r = httpx.request(m, API + p, timeout=k.pop("timeout", 90), **k)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(r.status_code, j)
    return j


def burn(path, tries=3):
    for _ in range(tries):
        try:
            with open(path, "rb") as f:
                return bridge("POST", "/api/v1/bitstream", files={"file": (path.split("/")[-1], f)}, timeout=600)
        except Exception as e:
            print("  burn retry:", str(e)[:60], flush=True)
            time.sleep(3)
    raise RuntimeError("burn failed " + path)


def wait_conn(ws, secs=15):
    e = time.time() + secs
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=0.5))
            if m.get("type") == "status" and m.get("state") == "connected":
                return True
        except Exception:
            pass
    return False


def drain(ws, secs):
    e = time.time() + secs
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=1.0))
        except Exception:
            continue
        t = m.get("type")
        if t == "rx":
            state["nk"] += (m.get("hex") or "").upper().count("4B")
            out.append(m.get("data_text") or "")
        elif t == "ack":
            print("  ack bytesSent=%s chunks=%s" % (m.get("bytesSent"), m.get("chunks")), flush=True)
        elif t == "error":
            print("  ERR %s" % str(m.get("reason"))[:90], flush=True)


app = open(APP, "rb").read()
expect_k = len(app) // 256 + 1
print("app %d bytes, expect %d K acks, segment=%d" % (len(app), expect_k, SEG), flush=True)
payload = b"R" + len(app).to_bytes(4, "little") + app
parts = [payload[i:i + SEG] for i in range(0, len(payload), SEG)]
print("segments:", [len(p) for p in parts], flush=True)

box = None
try:
    healthy = False
    for attempt in range(1, 7):
        try:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print(f"[{attempt}] box {box} ({r['device_name']})", flush=True)
            burn(BEACON)
            with connect(WS, open_timeout=20) as ws:
                ev = 0
                e = time.time() + 3
                while time.time() < e and ev < 2:
                    try:
                        m = json.loads(ws.recv(timeout=0.5))
                        if m.get("type") == "rx":
                            ev += 1
                    except Exception:
                        pass
            print("  beacon ev", ev, flush=True)
            if ev >= 2:
                healthy = True
                break
        except Exception as e:
            print("  hunt err", str(e)[:80], flush=True)
            time.sleep(2)
    if not healthy:
        print("ERROR no healthy box")
        raise SystemExit(1)

    burn(FIRMWARE)
    print("firmware burned; starting segmented upload", flush=True)
    t0 = time.time()
    for i, p in enumerate(parts):
        with connect(WS, open_timeout=20) as ws:
            if not wait_conn(ws):
                print("seg %d: no connect" % i)
                break
            ws.send(json.dumps({"type": "tx", "mode": "hex", "data": p.hex()}))
            drain(ws, 6 if i < len(parts) - 1 else 25)
        print("seg %d done at %.1fs nK=%d/%d" % (i, time.time() - t0, state["nk"], expect_k), flush=True)
        if i < len(parts) - 1:
            time.sleep(1.0)
    text = "".join(out)
    print("FINAL nK=%d/%d" % (state["nk"], expect_k), flush=True)
    print("tail:", repr(text[-200:]), flush=True)
    print("RESULT", "PASS" if ("BIG" in text and "OK" in text) else ("CHKFAIL" if "FAIL" in text else "NO_MARKER"), flush=True)
finally:
    try:
        bridge("POST", "/api/v1/devices/release", timeout=60)
        print("[release] ok")
    except Exception as e:
        print("[!] release failed", e)
