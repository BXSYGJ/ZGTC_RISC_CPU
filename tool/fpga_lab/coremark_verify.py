#!/usr/bin/env python3
"""coremark_verify.py — 端到端验证「511 分融合位流 + bootloader R 命令载 CoreMark」。

背景
----
融合系统 = 153MHz 高性能 CPU（RV32IM）+ 简化 bootloader（固化前 4KB，只保留 R 命令）+
应用 R 命令载入 0x1000 运行。本脚本一键完成：

  1. 找健康实验箱（beacon 门，自动避开坏箱）
  2. 烧 153MHz 融合位流（内含简化 bootloader）
  3. 串口连接，R 命令流控发 CoreMark .bin（256 字节块 + K 回执背压）
  4. CoreMark 打印 "READY send G" 后发 G 命令启动
  5. 读完整输出，解析 cycles_hex / retired_hex / clock_hz
  6. 计算分数 = iterations × clock_hz / cycles，校验 "Correct operation validated"

用法
----
  python coremark_verify.py
  python coremark_verify.py --iterations 6000 --read-tail 60

依赖：httpx、websockets.sync.client；桥接服务 127.0.0.1:8600 需已启动且已认证。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import httpx
from websockets.sync.client import connect

# Paths relative to this script so the workspace can move without edits.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(os.path.dirname(_HERE))

API = "http://127.0.0.1:8600"
WS = "ws://127.0.0.1:8600/ws/serial?baud=115200"
BEACON = os.path.join(_HERE, "test_designs", "uart_beacon", "generate_bitstream", "uart_beacon.sbit")
# 153MHz 融合位流（seed=1 收敛，WNS +0.018ns，LUT 9075/FF 4321）
FIRMWARE = os.path.join(
    _PROJECT, "cpu", "experiments", "full_fetch_commit_factored", "build", "pds",
    "20260912-214944-e6a316a5", "generate_bitstream", "pds_soc_top.sbit")
# CoreMark 应用（RV32IM O3 unroll relax 6000 迭代，ORIGIN=0x1000）
APP = os.path.join(_PROJECT, "cpu", "build", "coremark_app_i6000_rv32im.bin")
BLK = 256
READ_TAIL = 60.0  # CoreMark 6000 迭代约 12s 运行 + 启动 + 传输，留足余量


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
    """统计 hex 字节流中 0x4B('K') 回执的个数（非重叠 2-hex 子串）。"""
    up = (text_hex or "").upper()
    return sum(1 for i in range(0, max(0, len(up) - 1), 2) if up[i:i + 2] == "4B")


def find_healthy_box(attempts=7):
    """循环 release -> reserve -> 烧 beacon -> 读 rx，找能正常回传的箱子。"""
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


def fc_send(ws, app, block=256):
    """R 命令流控发送，返回 (送达成功?, K总数, 文本累积, hex累积)。

    简化 bootloader 收到 R + 4字节小端长度后，逐字节载入 0x1000；每收满
    256 字节回一个 K，最后再补一个 K；收到完整镜像后打印 "RUN\\r\\n" 并直接运行。
    """
    hdr = b"R" + len(app).to_bytes(4, "little")
    text_parts = []
    hex_parts = []
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
                hex_parts.append(m.get("hex") or "")
                text_parts.append(m.get("data_text") or "")
                state["k"] = count_acks("".join(hex_parts))
                return m
            elif t == "error":
                text_parts.append("[err]" + str(m.get("reason"))[:80])
        return None

    def send(data_hex):
        ws.send(json.dumps({"type": "tx", "mode": "hex", "data": data_hex}))

    send(hdr.hex())
    total = len(app)
    nk_prev = 0
    nblocks = 0
    ok = True
    for i in range(0, total, block):
        chunk = app[i:i + block]
        send(chunk.hex())
        nblocks += 1
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
    return ok, state["k"], "".join(text_parts), "".join(hex_parts)


def parse_coremark(text, iterations):
    """从累计输出解析 CoreMark 关键字段，返回 dict。"""
    res = {}
    res["text"] = text
    res["validated"] = "Correct operation validated" in text

    m = re.search(r"cycles_hex=([0-9a-fA-F]{16})", text)
    res["cycles_hex"] = m.group(1) if m else None
    m = re.search(r"retired_hex=([0-9a-fA-F]{16})", text)
    res["retired_hex"] = m.group(1) if m else None
    m = re.search(r"clock_hz=(\d+)", text)
    res["clock_hz"] = int(m.group(1)) if m else None
    m = re.search(r"config=([0-9a-fA-F]{8})", text)
    res["config"] = m.group(1) if m else None
    m = re.search(r"iterations=(\d+)", text)
    res["iterations"] = int(m.group(1)) if m else iterations

    if res["cycles_hex"] and res["clock_hz"]:
        cycles = int(res["cycles_hex"], 16)
        res["cycles_dec"] = cycles
        res["score"] = res["iterations"] * res["clock_hz"] / cycles
        res["score_mhz"] = res["score"] / (res["clock_hz"] / 1e6)
    else:
        res["cycles_dec"] = None
        res["score"] = None
        res["score_mhz"] = None
    return res


def main():
    ap = argparse.ArgumentParser(
        prog="coremark_verify.py",
        description="端到端验证 511 分融合位流 + bootloader R 命令载 CoreMark，计算精确分数。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--firmware", default=FIRMWARE, help="153MHz 融合位流 .sbit 路径")
    ap.add_argument("--app", default=APP, help="CoreMark 应用 .bin 路径")
    ap.add_argument("--block", type=int, default=BLK, help="流控块大小（默认 256）")
    ap.add_argument("--read-tail", type=float, default=READ_TAIL, help="发完后监听输出时长（秒）")
    ap.add_argument("--iterations", type=int, default=6000, help="CoreMark 迭代次数（解析回退值）")
    args = ap.parse_args()

    app = open(args.app, "rb").read()
    # 期望 K 数：bootloader 每收满 256 字节回一个 K，最后补一个 K。
    exp_k = len(app) // 256 + 1
    print("app %s (%d bytes) expect %d K" % (args.app, len(app), exp_k), flush=True)
    print("firmware %s" % args.firmware, flush=True)

    box = None
    try:
        box = find_healthy_box()
        if not box:
            print("RESULT=NO_HEALTHY_BOX", flush=True)
            return 1

        print("burn 153MHz fusion bitstream box %s" % box, flush=True)
        burn(args.firmware)

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
                return 3

            ok, k, out, hexacc = fc_send(ws, app, args.block)
            text_parts = [out]
            hex_parts = [hexacc]

            # 发完后监听。关键：CoreMark 打印 "READY send G" 后阻塞等 G(0x47)，
            # 而 READY 可能在 fc_send 的最后 K 等待期间就已到达并进了 text_parts，
            # 因此发 G 检查必须放在循环开头（每轮都查），不能依赖「收到新 rx」。
            g_sent = False
            tail_deadline = time.time() + args.read_tail
            while time.time() < tail_deadline:
                acc = "".join(text_parts)
                if not g_sent and ("send G" in acc or "READY" in acc):
                    ws.send(json.dumps({"type": "tx", "mode": "hex", "data": "47"}))
                    g_sent = True
                    print("  got READY -> sent G", flush=True)
                if "ZGTC COREMARK FINISHED" in acc:
                    break
                try:
                    m = json.loads(ws.recv(timeout=2.0))
                except Exception:
                    continue
                if m.get("type") == "rx":
                    text_parts.append(m.get("data_text") or "")
                    hex_parts.append(m.get("hex") or "")

        full_text = "".join(text_parts)
        full_hex = "".join(hex_parts)
        k = count_acks(full_hex)

        print("K acks: %d/%d (fc ok=%s, g_sent=%s)" % (k, exp_k, ok, g_sent), flush=True)
        print("---- CoreMark output tail ----", flush=True)
        print(full_text[-1200:], flush=True)
        print("---- end ----", flush=True)

        r = parse_coremark(full_text, args.iterations)
        status = "PASS" if (r["validated"] and r["score"] is not None) else "FAIL"
        print("validated=%s" % r["validated"], flush=True)
        if r["cycles_hex"]:
            print("cycles_hex=%s (%d)" % (r["cycles_hex"], r["cycles_dec"]), flush=True)
        if r["retired_hex"]:
            print("retired_hex=%s" % r["retired_hex"], flush=True)
        print("clock_hz=%s" % r["clock_hz"], flush=True)
        if r["score"] is not None:
            print("CoreMark=%.6f Iterations/Sec  (%.6f CoreMark/MHz)"
                  % (r["score"], r["score_mhz"]), flush=True)
        print("RESULT=%s" % status, flush=True)
        return 0 if status == "PASS" else 2
    finally:
        try:
            bridge("POST", "/api/v1/devices/release", timeout=60)
            print("[release] ok", flush=True)
        except Exception as exc:
            print("[!] release failed:", str(exc)[:100], flush=True)


if __name__ == "__main__":
    sys.exit(main())