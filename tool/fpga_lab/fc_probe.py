#!/usr/bin/env python3
"""fc_probe.py — 流控发送探测：验证「逐块发 + 等 K 回执」能否完整送达 app。

背景：现有 big_load.py / flash_boot_verify.py 一次性把整个 payload 通过一次
ws tx 发出，服务器内部分 1KB chunk 盲发（不关注板子回执）。实测 13KB 一次发
只送达 6.5~10.5KB（时变），判断是 platform 串口 tx 缓冲有限 + 无背压导致丢字节。
bootloader 每收 256 字节回一个 K(0x4B)，本脚本用 K 回执做流控：每发 256 字节
就等一个 K，确认送达后再发下一块。

用法：
  python fc_probe.py [app.bin] [block_bytes] [--flash]
默认 R 命令载 RAM（--flash 用 W 命令写 Flash）。
"""
import json
import sys
import time

import httpx
from websockets.sync.client import connect

API = "http://127.0.0.1:8600"
WS = "ws://127.0.0.1:8600/ws/serial?baud=115200"
BEACON = "D:/0000/111/001/Pango/tool/fpga_lab/test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
FIRMWARE = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/pds/20260907-195930-0a2aa5d6/generate_bitstream/pds_soc_top.sbit"
APP = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_big.bin"
BLK = 256
READ_TAIL = 25.0   # 发完后继续监听输出的时长（Flash 擦写 + 启动需要几秒）


def bridge(method, path, **kw):
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError("bridge %s %s: %s %s" % (method, path, r.status_code, j))
    return j


def burn(sbit, tries=3):
    last = None
    for _ in range(tries):
        try:
            with open(sbit, "rb") as f:
                return bridge("POST", "/api/v1/bitstream",
                              files={"file": (sbit.split("/")[-1], f)}, timeout=600)
        except Exception as exc:
            last = exc
            print("  burn retry:", str(exc)[:80], flush=True)
            time.sleep(3)
    raise RuntimeError("burn failed " + sbit) from last


def count_acks(text_hex):
    up = (text_hex or "").upper()
    return sum(1 for i in range(0, max(0, len(up) - 1), 2) if up[i:i + 2] == "4B")


def find_healthy_box(attempts=7):
    healthy = None
    for attempt_n in range(1, attempts + 1):
        try:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print("[%d] box %s (%s) beacon..." % (attempt_n, box, r.get("device_name", "?")), flush=True)
            burn(BEACON)
            ev = 0
            with connect(WS, open_timeout=20) as ws:
                e2 = time.time() + 4
                while time.time() < e2 and ev < 2:
                    try:
                        m = json.loads(ws.recv(timeout=0.5))
                    except Exception:
                        continue
                    if m.get("type") == "rx":
                        ev += 1
            if ev >= 2:
                print("  beacon ok (%d rx)" % ev, flush=True)
                healthy = box
                break
            print("  beacon dead (%d rx)" % ev, flush=True)
        except Exception as exc:
            print("  hunt err:", str(exc)[:80], flush=True)
            time.sleep(2)
    return healthy


def fc_send(ws, app, flash, block=256):
    """逐块发 + 等 K 回执，返回 (送达成功?, K总数, 输出文本, hex累积)。"""
    cmd = b"W" if flash else b"R"
    hdr = cmd + len(app).to_bytes(4, "little")
    out = []
    hexacc = []
    state = {"k": 0}

    def recv_one(timeout_s):
        e = time.time() + timeout_s
        while time.time() < e:
            try:
                m = json.loads(ws.recv(timeout=1.0))
            except Exception:
                continue
            t = m.get("type")
            if t == "rx":
                hexacc.append(m.get("hex") or "")
                out.append(m.get("data_text") or "")
                state["k"] = count_acks("".join(hexacc))
                return m
            elif t == "error":
                out.append("[err]" + str(m.get("reason"))[:80])
        return None

    def send(data_hex):
        ws.send(json.dumps({"type": "tx", "mode": "hex", "data": data_hex}))

    # 1) 发命令头 (cmd + 4字节长度)
    send(hdr.hex())
    # 2) 逐块发数据，每块等 K 递增
    total = len(app)
    nk_prev = 0
    nblocks = 0
    ok = True
    for i in range(0, total, block):
        chunk = app[i:i + block]
        send(chunk.hex())
        nblocks += 1
        # 等这一块对应的 K（K 总数至少比之前多 1）
        deadline = time.time() + 15
        got_new = False
        while time.time() < deadline and not got_new:
            recv_one(deadline - time.time())
            if state["k"] > nk_prev:
                got_new = True
        if not got_new:
            print("  [fc] block %d/%d no new K (got %d)" % (nblocks, (total + block - 1) // block, state["k"]), flush=True)
            ok = False
            break
        nk_prev = state["k"]
    return ok, state["k"], "".join(out), "".join(hexacc)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("app", nargs="?", default=APP)
    ap.add_argument("block", nargs="?", type=int, default=BLK)
    ap.add_argument("--flash", action="store_true")
    args = ap.parse_args()

    app_path = args.app
    blk = args.block
    flash = args.flash

    app = open(app_path, "rb").read()
    exp = len(app) // 256 + 1
    print("app %s (%d bytes) expect %d K, block=%d, mode=%s"
          % (app_path, len(app), exp, blk, "W(flash)" if flash else "R(ram)"), flush=True)

    box = None
    result = "UNKNOWN"
    try:
        box = find_healthy_box()
        if not box:
            print("ERROR no healthy box", flush=True)
            print("RESULT=NO_HEALTHY_BOX", flush=True)
            raise SystemExit(1)

        print("burn bootloader firmware box %s" % box, flush=True)
        burn(FIRMWARE)

        with connect(WS, open_timeout=20) as ws:
            # 等 connected
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
                print("RESULT=NOT_CONNECTED", flush=True)
                raise SystemExit(3)

            ok, k, out, hexacc = fc_send(ws, app, flash, blk)
            # 发完后继续读一段时间（Flash 擦写 / 应用启动输出）
            tail_deadline = time.time() + READ_TAIL
            while time.time() < tail_deadline:
                try:
                    m = json.loads(ws.recv(timeout=2.0))
                except Exception:
                    continue
                if m.get("type") == "rx":
                    out += (m.get("data_text") or "")
                    hexacc += (m.get("hex") or "")

        k = count_acks(hexacc)
        u = out.upper()
        print("K acks: %d/%d (blocks delivered ok=%s)" % (k, exp, ok), flush=True)
        print("reply tail:", repr(out[-250:]), flush=True)

        if k >= exp and "BIG" in u and "OK" in u:
            result = "PASS"
        elif k >= exp:
            result = "K_OK_NO_MARKER"
        elif "FAIL" in u:
            result = "CHK_FAIL"
        elif "BIG" in u or "FLASHED" in u:
            result = "PARTIAL"
        else:
            result = "NO_ACK"
        print("RESULT=%s" % result, flush=True)
        return 0 if result == "PASS" else 2
    finally:
        try:
            bridge("POST", "/api/v1/devices/release", timeout=60)
            print("[release] ok", flush=True)
        except Exception as exc:
            print("[!] release failed:", str(exc)[:100], flush=True)


if __name__ == "__main__":
    sys.exit(main())