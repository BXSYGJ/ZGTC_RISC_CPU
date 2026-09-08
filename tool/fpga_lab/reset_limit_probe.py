#!/usr/bin/env python3
"""判定「完整 release(销毁设备会话) + reserve(重建会话)」能否重置
「主机→板子」串口通道约 17KB 的单向累计上限。

背景
----
远程实验箱的主机→板子串口通道存在约 17KB 的单向累计上限，导致 33KB 固件
无法一次性下发。已知板子端 bootloader 每收 256 字节回一个 ``K``(0x4B)，
最后再补一个 ``K``；期望 K 数 = ``len(app)//256 + 1``。已证明「重开 WebSocket」
不会重置该上限。本脚本验证「完整 release + reserve」是否重置累计计数。

设计（决定性对比实验）
------------------------
把完整 payload 拆成多段，每段 < 16KB（默认 12000B）。每一轮 i 做：

    release(销毁会话) -> reserve(重建) -> burn(烧 bootloader 固件位流)
    -> 开 ws，用 R 命令把第 i 段载入 RAM -> drain 统计收到的 K -> 关 ws。

关键点：每段之间都会 burn 固件，从而复位板端 bootloader，使每一段都是一次
全新的、独立的 R 接收（不依赖跨段拼接）。因此：

* 若 release/reserve 每次重建都重置上限：每一段都能完整收到该段数据，
  该段 K 数接近 ``seg_len//256 + 1``，累计 K 随段数线性增长并明显超过
  单会话 17KB 上限（约 68 个 K）。
* 若上限跨 release/reserve 绑定（账号级或更底层）：第 2、3 段明显递减，
  累计 K 封顶在 ~17KB（约 68 个 K）。

运行（由 leader 在已认证 8600 桥接服务上执行，本脚本不写任何账号/密码）：
    python reset_limit_probe.py [app_path] [seg_bytes] [min_segments]
    python reset_limit_probe.py  # 默认用 app_huge.bin(33460B) 拆 3 段
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
APP = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_huge.bin"

BLOCK = 256
# 判定的「完整送达」阈值：该段实际 K / 期望 K 低于此值视为被截断
FULL_RATE = 0.85
# 「主机→板子」累计上限的参考值（17 * 1024 字节）——仅用于输出可读依据，不参与硬判定
LIMIT_BYTES = 17 * 1024


def bridge(method, path, **kw):
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError("bridge %s %s: %s %s" % (method, path, r.status_code, j))
    return j


def release():
    """销毁设备会话（忽略失败，确保幂等）。"""
    try:
        bridge("POST", "/api/v1/devices/release", timeout=60)
    except Exception as e:
        print("  [release] warn: %s" % str(e)[:80], flush=True)


def reserve(minutes=10):
    r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": minutes})
    return r


def burn(sbit, tries=3):
    for _ in range(tries):
        try:
            with open(sbit, "rb") as f:
                return bridge("POST", "/api/v1/bitstream",
                              files={"file": (sbit.split("/")[-1], f)}, timeout=600)
        except Exception as e:
            print("  burn retry: %s" % str(e)[:80], flush=True)
            time.sleep(3)
    raise RuntimeError("burn failed " + sbit)


def wait_conn(ws, secs=20):
    e = time.time() + secs
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=0.5))
            if m.get("type") == "status" and m.get("state") == "connected":
                return True
        except Exception:
            pass
    return False


def send_r_and_count(ws, seg):
    """发送一次独立 R 载入，返回 (实际K, 输出文本尾)。"""
    n = len(seg)
    payload = b"R" + n.to_bytes(4, "little") + seg
    ws.send(json.dumps({"type": "tx", "mode": "hex", "data": payload.hex()}))
    nk = 0
    out = []
    # drain 时长：至少 6s，按 115200 baud 估算数据发送时间并留余量
    secs = max(6.0, n * 12.0 / 115200.0 + 3.0)
    e = time.time() + secs
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=1.0))
        except Exception:
            continue
        t = m.get("type")
        if t == "rx":
            nk += (m.get("hex") or "").upper().count("4B")
            out.append(m.get("data_text") or "")
        elif t == "ack":
            print("    ack bytesSent=%s chunks=%s" % (m.get("bytesSent"), m.get("chunks")), flush=True)
        elif t == "error":
            print("    ERR %s" % str(m.get("reason"))[:90], flush=True)
    return nk, "".join(out)


def run_segment(idx, seg):
    """一轮独立实验：release -> reserve -> burn -> 开 ws 发一段 -> 数 K。"""
    seg_bytes = len(seg)
    expect_k = seg_bytes // BLOCK + 1
    print("[seg %d] %d bytes, expect K=%d" % (idx, seg_bytes, expect_k), flush=True)

    # 1) 销毁会话
    print("  release...", flush=True)
    release()

    # 2) 重建会话
    box = None
    for attempt in range(1, 4):
        try:
            r = reserve()
            box = r["box_id"]
            print("  reserved box %s (%s)" % (box, r.get("device_name", "?")), flush=True)
            break
        except Exception as e:
            print("  reserve retry %d: %s" % (attempt, str(e)[:80]), flush=True)
            time.sleep(2)
    if box is None:
        return {"seg": idx, "bytes": seg_bytes, "expect_k": expect_k, "k": -1, "rate": 0.0}

    # 3) 烧 bootloader 固件位流（复位板端，让每段都是一次全新 R 接收）
    print("  burn firmware...", flush=True)
    burn(FIRMWARE)

    # 4) 开 ws 发该段并统计 K
    nk = -1
    out = ""
    hit = time.time() + 20
    while time.time() < hit:
        try:
            with connect(WS, open_timeout=20) as ws:
                if not wait_conn(ws):
                    print("  no serial connect", flush=True)
                    raise RuntimeError("serial not connected")
                nk, out = send_r_and_count(ws, seg)
                break
        except Exception as e:
            print("  segment error: %s" % str(e)[:100], flush=True)
            time.sleep(2)

    rate = nk / expect_k if (nk >= 0 and expect_k > 0) else 0.0
    tail = repr(out[-120:]) if out else ""
    print("  got K=%d (rate=%.2f) tail=%s" % (nk, rate, tail), flush=True)
    return {"seg": idx, "bytes": seg_bytes, "expect_k": expect_k, "k": nk, "rate": rate}


def main():
    app_path = sys.argv[1] if len(sys.argv) > 1 else APP
    seg_size = int(sys.argv[2]) if len(sys.argv) > 2 else 12000
    min_segs = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    app = open(app_path, "rb").read()
    # 若段数不足 min_segs，自动缩段长，保证至少 min_segs 段
    while (len(app) + seg_size - 1) // seg_size < min_segs and seg_size > BLOCK:
        seg_size = max(BLOCK, seg_size // 2)
    parts = [app[i:i + seg_size] for i in range(0, len(app), seg_size)]
    if len(parts) < min_segs:
        print("ERROR: app too small to split into %d segments (size=%d)" % (min_segs, len(app)))
        raise SystemExit(1)

    print("app %s (%d bytes) -> %d segments of <=%d bytes" % (app_path, len(app), len(parts), seg_size), flush=True)
    print("FULL_RATE=%.2f  LIMIT_BYTES=%d (ref K~%d)" % (FULL_RATE, LIMIT_BYTES, LIMIT_BYTES // BLOCK), flush=True)

    results = []
    try:
        for i, p in enumerate(parts):
            results.append(run_segment(i, p))
            time.sleep(1.0)
    finally:
        try:
            bridge("POST", "/api/v1/devices/release", timeout=60)
            print("[release] ok", flush=True)
        except Exception as e:
            print("[!] release failed: %s" % str(e)[:100], flush=True)

    # ---- 汇总与判定 ----
    print("\n==== summary ====", flush=True)
    cum = 0
    total_k = 0
    reset_expect = 0
    full_segs = 0
    for r in results:
        cum += r["bytes"]
        total_k += max(0, r["k"])
        reset_expect += r["expect_k"]
        if r["rate"] >= FULL_RATE:
            full_segs += 1
        print("seg %d: sent=%6dB cum=%6dB  K=%3d/%3d  rate=%.2f"
              % (r["seg"], r["bytes"], cum, r["k"], r["expect_k"], r["rate"]), flush=True)

    limit_k_ref = LIMIT_BYTES // BLOCK  # 68
    print("totalK=%d  reset_expect_totalK=%d  single_session_refK~%d"
          % (total_k, reset_expect, limit_k_ref), flush=True)
    print("full_segments=%d/%d" % (full_segs, len(results)), flush=True)

    if full_segs == len(results):
        result = "RESETTABLE"
        reason = ("每段都拿到该段应有的完整 K(rate>=%.2f)，累计 K=%d 明显超过单会话 17KB 上限(约 %d 个 K)，"
                  "说明 release/reserve 每次重建会话都重置了累计上限，可分段拼出大文件"
                  % (FULL_RATE, total_k, limit_k_ref))
    else:
        result = "NOT_RESETTABLE"
        reason = ("后续段 K 明显递减，累计封顶在 ~17KB(单会话约 %d 个 K)，"
                  "说明上限跨 release/reserve 绑定（账号级或更底层）" % limit_k_ref)

    print("RESULT=%s" % result, flush=True)
    print("REASON: %s" % reason, flush=True)


if __name__ == "__main__":
    main()