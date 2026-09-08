"""stream_load.py — 串口烧录场景的「客户端只发、服务器分块」实测脚本。

背景：桥接服务器（fpga_lab_server/app.py）已在串口 WS 上实现了
  - RX 排空：后台持续读到 4096B、突发排空，回传不再丢；
  - TX 分块流控：大包 >1KB 自动按 ~1KB 分块、按 115200 波特率节奏流式下发，
    回 tx_progress 进度 + 最终 ack。
因此客户端**只需一次性把整个字节流发出去**，无需自己分块。

本脚本完成一次完整烧录实测并给出稳定性指标：
  release -> (reserve -> burn beacon -> 验串口) 找健康箱
   -> burn bootloader 固件 -> 一次 WS tx 下发「R + 4字节小端长度 + 整个 app」
   -> 收集回传，统计 K(0x4B) 回执与丢失率、捕获成功/失败标记 -> release。

用法（需在 127.0.0.1:8600 已起 bridge server）：
  python stream_load.py --app <app.bin> --firmware <bootloader.sbit> [--beacon <beacon.sbit>]
输出最后一行 RESULT=PASS|... 与丢包统计。
"""
from __future__ import annotations

import argparse
import json
import time

import httpx
from websockets.sync.client import connect

API = "http://127.0.0.1:8600"
BEACON = "test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
BLOCK = 256          # bootloader 每收 256B 回一个 K(0x4B)
READ_WINDOW_S = 40.0  # 发送后回传收集窗口（容忍平台数秒静默 + 突发回传）


def build_upload_payload(app: bytes) -> bytes:
    """R 命令 + 4字节小端长度 + 整个 app 数据，作为单个连续字节流。"""
    return b"R" + len(app).to_bytes(4, "little") + app


def count_acks(text_hex: str) -> int:
    """统计 hex 字节流里 0x4B（'K'）回执的个数（非重叠 2-hex 子串）。"""
    up = (text_hex or "").upper()
    return sum(1 for i in range(0, max(0, len(up) - 1), 2) if up[i:i + 2] == "4B")


def expected_acks(app_len: int) -> int:
    # 固件侧：每「满」256B 回一个 K，最后再补一个 K → floor(len/256)+1
    # 实测锚点：33380B → 131，10936B → 43
    return app_len // BLOCK + 1


def bridge(method, path, **kw):
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"bridge {method} {path}: {r.status_code} {j}")
    return j


def burn(sbit):
    with open(sbit, "rb") as f:
        return bridge("POST", "/api/v1/bitstream",
                      files={"file": (sbit.split("/")[-1], f)}, timeout=600)


def find_healthy_box(beacon, attempts=7):
    healthy = None
    for attempt_n in range(1, attempts + 1):
        try:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print(f"[{attempt_n}] box {box} ({r['device_name']}) beacon...", flush=True)
            burn(beacon)
            ev = 0
            with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
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
                healthy = box
                break
            print(f"  beacon dead ({ev} events)", flush=True)
        except Exception as exc:
            print(f"  attempt error: {exc}", flush=True)
            time.sleep(2)
    return healthy


def stream_upload(app: bytes):
    """一次 WS tx 下发整个字节流，收集回传并统计。"""
    payload = build_upload_payload(app)
    exp = expected_acks(len(app))
    boxes = []
    rx_events = 0
    out = []
    hexacc = []
    ack_info = None
    with connect("ws://127.0.0.1:8600/ws/serial?baud=115200", open_timeout=20) as ws:
        connected = False
        e = time.time() + 15
        while time.time() < e and not connected:
            try:
                m = json.loads(ws.recv(timeout=0.5))
                if m.get("type") == "status" and m.get("state") == "connected":
                    connected = True
                    boxes.append(m.get("box_id"))
            except Exception:
                pass
        if not connected:
            return {"ok": False, "result": "NOT_CONNECTED"}

        t0 = time.time()
        ws.send(json.dumps({"type": "tx", "mode": "hex", "data": payload.hex()}))
        deadline = time.time() + READ_WINDOW_S
        while time.time() < deadline:
            try:
                m = json.loads(ws.recv(timeout=2.0))
            except Exception:
                continue
            t = m.get("type")
            if t == "ack":
                ack_info = m
            elif t == "rx":
                rx_events += 1
                out.append(m.get("data_text") or "")
                hexacc.append(m.get("hex") or "")
        try:
            ws.send(json.dumps({"type": "close"}))
        except Exception:
            pass

    joined = "".join(out)
    k = count_acks("".join(hexacc))
    return {
        "ok": True, "result": None, "rx_events": rx_events, "ack_info": ack_info,
        "k_received": k, "k_expected": exp, "loss_pct": round(max(0, exp - k) * 100.0 / max(1, exp), 1),
        "elapsed_s": round(time.time() - t0, 2), "output": joined,
    }


def classify(output: str) -> str:
    u = output.upper()
    if "ERR" in u:
        return "RX_ERR"
    if "FAIL" in u:
        return "CHECKSUM_FAIL"
    if "OK" in u and "RUN" in u:
        return "PASS"
    if "OK" in u and "BIG" in u:
        return "PASS"
    if "HELLO" in u:
        return "PASS"
    return "NO_MARKER"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, help="app .bin to load into RAM")
    ap.add_argument("--firmware", required=True, help="bootloader .sbit already built")
    ap.add_argument("--beacon", default=BEACON)
    ap.add_argument("--attempts", type=int, default=7)
    args = ap.parse_args()

    app = open(args.app, "rb").read()
    print(f"app size {len(app)} bytes; expect ~{expected_acks(len(app))} K acks", flush=True)

    box = None
    try:
        box = find_healthy_box(args.beacon, args.attempts)
        if not box:
            print("ERROR no healthy box", flush=True)
            raise SystemExit(1)

        print(f"burn bootloader firmware box {box}", flush=True)
        burn(args.firmware)

        res = stream_upload(app)
        if not res["ok"]:
            print("RESULT=NOT_CONNECTED", flush=True)
            raise SystemExit(3)

        ack = res["ack_info"] or {}
        result = classify(res["output"])
        print(f"rx events:          {res['rx_events']}", flush=True)
        print(f"K acks:             {res['k_received']}/{res['k_expected']} "
              f"(loss {res['loss_pct']}%)", flush=True)
        print(f"server tx ack:      bytesSent={ack.get('bytesSent')} "
              f"chunks={ack.get('chunks')} elapsed={ack.get('elapsed_s')}s", flush=True)
        print(f"upload elapsed:     {res['elapsed_s']}s", flush=True)
        print("reply tail:", repr(res["output"][-250:]), flush=True)
        print(f"RESULT={result}", flush=True)
        return 0 if result == "PASS" else 2
    finally:
        try:
            bridge("POST", "/api/v1/devices/release", timeout=60)
            print("[release] ok", flush=True)
        except Exception as e:
            print("[!] release failed", e, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())