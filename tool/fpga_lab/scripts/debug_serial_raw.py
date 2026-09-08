"""debug_serial_raw.py — 绕过桥接，直接看平台 serial read 的原始返回，判定失败根因。

对每次预约到的箱子：烧信标 -> open serial -> 20s 内每 0.7s read 一次，打印每条原始响应
(hasData/bytesRead/hex 长度/diagnostic/allZeroPayload/异常)。
用法：python debug_serial_raw.py [--max-rounds 5] [--seconds 20]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # fpga_lab/

import httpx

from fpga_lab_server.paths import ACCOUNT_FILE
from fpga_lab_server.platform import PlatformClient, PlatformError

BEACON = Path("test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rounds", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    pc = PlatformClient()
    try:
        cred = [ln.strip() for ln in ACCOUNT_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
        pc.login(cred[0], cred[1])
        print("login ok")

        for rnd in range(1, args.max_rounds + 1):
            try:
                pc.release_current()
            except Exception:
                pass
            try:
                d = pc.reserve(10)
            except PlatformError as e:
                print(f"[{rnd}] reserve error: {e}")
                time.sleep(1)
                continue
            box = d.get("deviceId")
            print(f"\n[{rnd}] box={box} ({d.get('deviceName')})", flush=True)

            pc.burn_and_wait(box, BEACON)
            print(f"  burn done", flush=True)

            try:
                st = pc.serial_open(box)
                print(f"  open -> {st}", flush=True)
            except PlatformError as e:
                print(f"  open ERROR: {e}")
                try:
                    pc.release_current()
                except Exception:
                    pass
                continue

            data_reads = 0
            empty = 0
            diag = 0
            err = None
            t0 = time.time()
            while time.time() - t0 < args.seconds:
                time.sleep(0.7)
                try:
                    rd = pc.serial_read(box, length=64)
                except PlatformError as e:
                    err = str(e)
                    print(f"  read ERROR: {e}", flush=True)
                    break
                hx = rd.get("hex") or ""
                if rd.get("hasData") or rd.get("bytesRead"):
                    data_reads += 1
                    if data_reads <= 3:
                        print(f"  read[{data_reads}] DATA bytesRead={rd.get('bytesRead')} hex[:64]={hx[:64]}", flush=True)
                else:
                    empty += 1
                    if rd.get("allZeroPayload"):
                        diag += 1
                    if (empty + data_reads) % 10 == 0:
                        print(f"  ... empty reads={empty} data={data_reads} allZeroDiag={diag}", flush=True)
            print(f"[{rnd}] box={box} result: data_reads={data_reads} empty={empty} allZeroDiag={diag} err={err}", flush=True)

            try:
                pc.serial_close(box)
                pc.release_current()
            except Exception:
                pass
    finally:
        try:
            pc.release_current()
        except Exception:
            pass
        pc.close()


if __name__ == "__main__":
    main()
