"""Load a large app (32 KiB) into RAM via the bootloader 'R' command using the
per-256-byte 'K' ack protocol, and verify the on-board checksum output."""
import json
import time
import httpx
from websockets.sync.client import connect

API = "http://127.0.0.1:8600"
BEACON = "D:/0000/111/001/Pango/tool/fpga_lab/test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
FIRMWARE = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/pds/20260907-195930-0a2aa5d6/generate_bitstream/pds_soc_top.sbit"
APP = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_big.bin"
BLOCK = 256


def bridge(method, path, **kw):
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"bridge {method} {path}: {r.status_code} {j}")
    return j


def burn(sbit):
    with open(sbit, "rb") as f:
        return bridge("POST", "/api/v1/bitstream", files={"file": (sbit.split("/")[-1], f)}, timeout=600)


def tx(ws, data_hex):
    ws.send(json.dumps({"type": "tx", "mode": "hex", "data": data_hex}))


def count_acks(text_hex):
    up = (text_hex or "").upper()
    return sum(1 for i in range(0, max(0, len(up) - 1), 2) if up[i:i + 2] == "4B")


def upload_and_run(ws, app):
    """Stream the whole image paced to 115200 baud, then read output.
    Returns (rx_events, output_text)."""
    n = len(app)
    connected = False
    e = time.time() + 15
    while time.time() < e and not connected:
        try:
            m = json.loads(ws.recv(timeout=0.5))
            if m.get("type") == "status" and m.get("state") == "connected":
                connected = True
        except Exception:
            pass
    if not connected:
        return False, "serial not connected"
    # The server streams large payloads internally (1 KiB chunks paced to the
    # baud rate), so hand it the whole image in a single tx.
    payload = b"R" + len(app).to_bytes(4, "little") + app
    tx(ws, payload.hex())
    print("sent %d bytes in one tx; server streams it" % len(payload), flush=True)
    # read the resulting output (acks arrive batched; keep listening to deadline)
    out = []
    ev = 0
    nk = 0
    e = time.time() + 40
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=2.0))
        except Exception:
            continue
        t = m.get("type")
        if t == "tx_progress":
            print("  progress %s/%s total=%s" % (m.get("index"), m.get("total"), m.get("totalSent")), flush=True)
        elif t == "ack":
            print("  ack bytesSent=%s chunks=%s elapsed=%s" % (m.get("bytesSent"), m.get("chunks"), m.get("elapsed_s")), flush=True)
        elif t == "error":
            print("  server error: %s" % str(m.get("reason"))[:120], flush=True)
        elif t == "rx":
            ev += 1
            nk += (m.get("hex") or "").upper().count("4B")
            out.append(m.get("data_text") or "")
    print("  K acks=%d (expect %d) rx_events=%d" % (nk, len(app) // BLOCK + 1, ev), flush=True)
    return ev, "".join(out)


app = open(APP, "rb").read()
print(f"app size {len(app)} bytes", flush=True)

box = None
try:
    healthy = False
    for attempt_n in range(1, 8):
        try:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print(f"[{attempt_n}] box {box} ({r['device_name']}) beacon...", flush=True)
            burn(BEACON)
            with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
                ev = 0
                e2 = time.time() + 4
                while time.time() < e2 and ev < 2:
                    try:
                        m = json.loads(ws.recv(timeout=0.5))
                    except Exception:
                        continue
                    if m.get("type") == "rx":
                        ev += 1
            if ev >= 2:
                print(f"  beacon ok ({ev} rx events)", flush=True)
                healthy = True
                break
            print(f"  beacon dead ({ev} events)", flush=True)
        except Exception as exc:
            print(f"  attempt error: {exc}", flush=True)
            time.sleep(2)
    if not healthy:
        print("ERROR no healthy box")
        raise SystemExit(1)

    print(f"burn bootloader firmware box {box}", flush=True)
    result = "UNKNOWN"
    for up_try in range(1, 4):
        try:
            burn(FIRMWARE)
            print(f"send big app with block acks (try {up_try}) ...", flush=True)
            with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
                ev, out = upload_and_run(ws, app)
            print("reply:", repr(out[-250:]), flush=True)
            if (("BIG" in out or "MID" in out) and "OK" in out):
                result = "PASS"
                break
            if "FAIL" in out:
                result = "CHECKSUM_FAIL"
                break
            if "ERR" in out:
                result = "RX_ERR"
            else:
                result = "NO_MARKER"
        except Exception as exc:
            print(f"  upload error: {exc}", flush=True)
            result = "RETRY"
        time.sleep(2)
    print("RESULT=%s" % result, flush=True)
finally:
    try:
        bridge("POST", "/api/v1/devices/release", timeout=60)
        print("[release] ok")
    except Exception as e:
        print("[!] release failed", e)
