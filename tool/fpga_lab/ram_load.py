#!/usr/bin/env python3
"""ram_load.py — 远程实验箱「流控发送 + 载 RAM 运行」正式命令。

背景
----
PG2L200H 上 RV32I SoC 的 bootloader 通过 UART（115200 8N1）接收程序：
  - R<len32><bin>  载入 RAM 直接运行（断电丢失，快速迭代）
  - W<len32><bin>  写 U9 Flash 并启动（持久化，当前受 H13 专用引脚限制不可行）
bootloader 每收满 256 字节回一个 K(0x4B)，最后再补一个 K。

旧脚本（big_load.py 等）一次性盲发整个 payload，导致 platform 串口 tx 缓冲溢出、
时变丢字节（13KB 实测只送达 6.5~10.5KB）。本脚本用 K 回执做流控（背压）：
逐块发 256 字节 → 等一个 K 回执 → 再发下一块，已实测成功送达 13KB 与 33KB。

用法
----
  # 默认 R 命令载 RAM（13KB app_big.bin）
  python ram_load.py

  # 指定大文件（33KB app_huge.bin）
  python ram_load.py D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_huge.bin

  # 自定义流控块大小（默认 256，应为 256 的整数倍）
  python ram_load.py --block 512

  # 尝试 W 命令写 Flash（**当前板子不可行，会报 ERR erase**）
  python ram_load.py --flash

依赖：httpx、websockets.sync.client（桥接服务 127.0.0.1:8600 需已起且已认证）
"""
from __future__ import annotations

import argparse
import json
import os
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
FIRMWARE = os.path.join(_PROJECT, "cpu", "build", "pds", "20260907-195930-0a2aa5d6", "generate_bitstream", "pds_soc_top.sbit")
APP = os.path.join(_PROJECT, "cpu", "build", "app_big.bin")
BLK = 256
READ_TAIL = 25.0  # 发完后继续监听输出的时长（Flash 擦写 + 启动需数秒）


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


def classify_result(output, k_received, k_expected, flash):
    """按输出与 K 回执判读烧录结果。"""
    u = output.upper()
    has_big = "BIG" in u
    has_ok = "OK" in u
    has_fail = "FAIL" in u
    has_flashed = "FLASHED" in u
    has_err_erase = "ERR" in u and "ERASE" in u

    if has_big and has_ok:
        if k_received >= k_expected:
            return "PASS"
        return "PASS_ACK_SHORT"  # 功能 OK，K 回执略缺（多为回传统计偏差）
    if has_fail:
        return "CHK_FAIL"
    if flash and has_err_erase:
        return "FLASH_ERASE_FAIL"  # W 命令写 Flash 受 H13 限制，当前不可行
    if has_flashed:
        return "FLASHED_FAIL"  # Flash 擦写完成但应用未正常启动
    if k_received < k_expected:
        return "NO_ACK"  # 数据未收全（K 回执不足）
    return "NO_MARKER"


def main():
    ap = argparse.ArgumentParser(
        prog="ram_load.py",
        description="远程实验箱「流控发送 + 载 RAM 运行」正式命令。逐块发 + 等 K 回执，避免盲发丢字节。",
        epilog=(
            "示例：\n"
            "  python ram_load.py                                    # R 命令载 13KB 默认 app\n"
            "  python ram_load.py app_huge.bin                       # R 命令载 33KB 大文件\n"
            "  python ram_load.py --block 512                        # 自定义流控块大小\n"
            "  python ram_load.py --flash                            # 尝试 W 写 Flash（当前不可行）\n\n"
            "注意：--flash 走 W 命令写 U9 Flash，当前板子受 H13 专用引脚限制，\n"
            "      软 SPI 物理够不到 U9，bootloader 擦写会报 ERR erase。\n"
            "      当前交付路径为 R 命令载 RAM（断电丢失，但换程序快速）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("app", nargs="?", default=APP, help="应用 .bin 路径（默认 app_big.bin）")
    ap.add_argument("--block", type=int, default=BLK, help="流控块大小（默认 256，应为 256 的整数倍）")
    ap.add_argument("--flash", action="store_true", help="走 W 命令写 Flash（当前不可行）")
    args = ap.parse_args()

    app_path = args.app
    blk = args.block
    flash = args.flash

    app = open(app_path, "rb").read()
    # 期望 K 数：bootloader 每 256 字节回一个 K，最后补一个 K
    exp = (len(app) + 255) // 256 + 1
    mode = "W(flash)" if flash else "R(ram)"
    print("app %s (%d bytes) expect %d K, block=%d, mode=%s"
          % (app_path, len(app), exp, blk, mode), flush=True)

    if flash:
        print("WARNING: --flash 走 W 命令写 U9 Flash，当前板子受 H13 专用引脚限制，软 SPI 物理够不到 U9，"
              "bootloader 擦写会报 ERR erase。当前交付路径为 R 命令载 RAM。", flush=True)

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
        result = classify_result(out, k, exp, flash)
        print("K acks: %d/%d (blocks delivered ok=%s)" % (k, exp, ok), flush=True)
        print("reply tail:", repr(out[-250:]), flush=True)
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