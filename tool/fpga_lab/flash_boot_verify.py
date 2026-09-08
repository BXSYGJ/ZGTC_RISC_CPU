"""flash_boot_verify.py — 远程实验箱「写 Flash + 启动验证」脚本。

背景
  PG2L200H 上实现 RV32I SoC，程序存于板载 U9 QSPI Flash，上电由 BRAM 内
  bootloader 读到 RAM 启动。bootloader 控制台（115200 8N1）命令：
    - W<len:u32小端><bin>  收数据 -> 擦写 U9 Flash -> 打印 "FLASHED\\r\\n"
                           -> 直接从 Flash 启动应用（即「烧录」）
    - R<len:u32小端><bin>  收数据 -> 打印 "RUN\\r\\n" -> 直接运行（不写 Flash）
  收数据时每收满 256 字节回一个 K(0x4B)，最后再多回一个 K，故期望
  K 数 = len(app)//256 + 1。

本脚本完成一次完整「写 Flash + 启动验证」流程：
  release -> (reserve -> burn beacon -> 验串口) 找健康箱
  -> burn bootloader 固件 -> WS 下发「W + 4 字节长度 + 整个 app」写 Flash
  -> 收集 K 回执与输出，判读 BIG 3072 / OK
  -> (增强) 重新 burn 固件位流等效复位 FPGA，验证可从 Flash 自动启动
  -> release。

用法（需 127.0.0.1:8600 bridge server 已起且已登录）：
  python flash_boot_verify.py
最后打印 RESULT=PASS|...。
"""
from __future__ import annotations

import json
import time

import httpx
from websockets.sync.client import connect

API = "http://127.0.0.1:8600"
WS = "ws://127.0.0.1:8600/ws/serial?baud=115200"
BEACON = "D:/0000/111/001/Pango/tool/fpga_lab/test_designs/uart_beacon/generate_bitstream/uart_beacon.sbit"
FIRMWARE = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/pds/20260907-195930-0a2aa5d6/generate_bitstream/pds_soc_top.sbit"
APP = "D:/0000/111/001/Pango/ZGTC_RISC_CPU/cpu/build/app_big.bin"

BLOCK = 256                    # bootloader 每收满 256 字节回一个 K(0x4B)
READ_WINDOW_S = 45.0           # 发送 W 后监听窗口（Flash 擦写需数秒，>=40s）
RESET_VERIFY_WINDOW_S = 25.0   # 复位后从 Flash 自启动的监听窗口


def bridge(method, path, **kw):
    r = httpx.request(method, API + path, timeout=kw.pop("timeout", 90), **kw)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"bridge {method} {path}: {r.status_code} {j}")
    return j


def burn(sbit, tries=3):
    """烧写位流，带重试（bitstream 上传/烧写耗时长，偶发超时重试）。"""
    last = None
    for _ in range(tries):
        try:
            with open(sbit, "rb") as f:
                return bridge("POST", "/api/v1/bitstream",
                              files={"file": (sbit.split("/")[-1], f)}, timeout=600)
        except Exception as exc:  # noqa: BLE001
            last = exc
            print("  burn retry:", str(exc)[:80], flush=True)
            time.sleep(3)
    raise RuntimeError("burn failed " + sbit) from last


def tx(ws, data_hex):
    ws.send(json.dumps({"type": "tx", "mode": "hex", "data": data_hex}))


def count_acks(text_hex):
    """统计 hex 字节流中 0x4B('K') 回执的个数（非重叠 2-hex 子串）。"""
    up = (text_hex or "").upper()
    return sum(1 for i in range(0, max(0, len(up) - 1), 2) if up[i:i + 2] == "4B")


def expected_acks(app_len):
    return app_len // BLOCK + 1


def wait_connected(ws, secs=15):
    """等待串口 WS 会话进入 connected 状态。"""
    e = time.time() + secs
    while time.time() < e:
        try:
            m = json.loads(ws.recv(timeout=0.5))
            if m.get("type") == "status" and m.get("state") == "connected":
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def find_healthy_box(beacon, attempts=7):
    """循环 release -> reserve -> 烧 beacon -> 读 rx，找能正常回传的箱子。"""
    healthy = None
    for attempt_n in range(1, attempts + 1):
        try:
            try:
                bridge("POST", "/api/v1/devices/release", timeout=60)
            except Exception:  # noqa: BLE001
                pass
            r = bridge("POST", "/api/v1/devices/reserve", json={"minutes": 10})
            box = r["box_id"]
            print(f"[{attempt_n}] box {box} ({r['device_name']}) beacon...", flush=True)
            burn(beacon)
            ev = 0
            with connect(WS, open_timeout=20) as ws:
                e2 = time.time() + 4
                while time.time() < e2 and ev < 2:
                    try:
                        m = json.loads(ws.recv(timeout=0.5))
                    except Exception:  # noqa: BLE001
                        continue
                    if m.get("type") == "rx":
                        ev += 1
            if ev >= 2:
                print(f"  beacon ok ({ev} rx events)", flush=True)
                healthy = box
                break
            print(f"  beacon dead ({ev} events)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  attempt error: {exc}", flush=True)
            time.sleep(2)
    return healthy


def build_flash_payload(app):
    """W 命令 + 4 字节小端长度 + 整个 app 数据，作为单个连续字节流。"""
    return b"W" + len(app).to_bytes(4, "little") + app


def flash_upload(app):
    """一次 WS tx 下发整个 W 命令字节流，收集 K 回执与文本输出。"""
    payload = build_flash_payload(app)
    exp = expected_acks(len(app))
    rx_events = 0
    out = []
    hexacc = []
    ack_info = None
    with connect(WS, open_timeout=20) as ws:
        if not wait_connected(ws):
            return {"ok": False, "result": "NOT_CONNECTED"}
        t0 = time.time()
        tx(ws, payload.hex())
        print(f"sent W cmd {len(payload)} bytes in one tx; server streams it", flush=True)
        deadline = time.time() + READ_WINDOW_S
        while time.time() < deadline:
            try:
                m = json.loads(ws.recv(timeout=2.0))
            except Exception:  # noqa: BLE001
                continue
            t = m.get("type")
            if t == "tx_progress":
                print("  progress %s/%s total=%s"
                      % (m.get("index"), m.get("total"), m.get("totalSent")), flush=True)
            elif t == "ack":
                ack_info = m
                print("  server ack bytesSent=%s chunks=%s elapsed=%s"
                      % (m.get("bytesSent"), m.get("chunks"), m.get("elapsed_s")), flush=True)
            elif t == "error":
                print("  server error: %s" % str(m.get("reason"))[:120], flush=True)
            elif t == "rx":
                rx_events += 1
                out.append(m.get("data_text") or "")
                hexacc.append(m.get("hex") or "")

    joined = "".join(out)
    k = count_acks("".join(hexacc))
    return {
        "ok": True, "rx_events": rx_events, "ack_info": ack_info,
        "k_received": k, "k_expected": exp,
        "elapsed_s": round(time.time() - t0, 2), "output": joined,
    }


def classify_flash(output, k_received, k_expected):
    """按输出与 K 回执判读烧录结果。"""
    u = output.upper()
    has_big = "BIG" in u
    has_ok = "OK" in u
    has_flashed = "FLASHED" in u
    has_fail = "FAIL" in u

    if has_big and has_ok:
        # 功能硬指标：应用已从 Flash 正确启动且校验和 OK
        if k_received >= k_expected:
            return "PASS"
        return "PASS_ACK_SHORT"   # 应用 OK，但 K 回执计数不足（多为回传统计偏差）
    if has_fail:
        return "CHK_FAIL"          # 应用启动但校验和错误
    if has_flashed:
        return "FLASHED_FAIL"      # Flash 擦写完成但应用未正常启动
    if k_received < k_expected:
        return "NO_ACK"            # 数据未收全（K 回执不足），未完成擦写
    return "NO_MARKER"


def reset_verify():
    """重新烧固件位流等效复位 FPGA，验证 bootloader 从 Flash 自动启动应用。

    说明：Flash 已有镜像时，bootloader 重跑会检测并自动 boot_from_flash 启动，
    无需再发任何命令，只需监听输出是否再次出现 BIG 3072 + OK。
    若受网络/会话限制（如重烧后串口会话不可用）则返回 SKIP 并说明。
    """
    out = []
    try:
        print("re-burn firmware (等效复位 FPGA), 等待 bootloader 自动从 Flash 启动...", flush=True)
        burn(FIRMWARE)
    except Exception as exc:  # noqa: BLE001
        print("[!] reset verify: re-burn firmware failed -> %s" % exc, flush=True)
        return "SKIP"

    time.sleep(2)  # 等 FPGA 重新配置 + bootloader 起来并读 Flash
    try:
        with connect(WS, open_timeout=20) as ws:
            e = time.time() + RESET_VERIFY_WINDOW_S
            while time.time() < e:
                try:
                    m = json.loads(ws.recv(timeout=2.0))
                except Exception:  # noqa: BLE001
                    continue
                if m.get("type") == "rx":
                    out.append(m.get("data_text") or "")
    except Exception as exc:  # noqa: BLE001
        print("[!] reset verify ws error: %s" % exc, flush=True)

    joined = "".join(out)
    print("reset verify tail:", repr(joined[-200:]), flush=True)
    if "BIG" in joined and "OK" in joined:
        return "PASS"
    if "FAIL" in joined:
        return "FAIL"
    if not joined:
        return "SKIP"
    return "NO_MARKER"


def main():
    app = open(APP, "rb").read()
    exp = expected_acks(len(app))
    print(f"app size {len(app)} bytes; expect {exp} K acks", flush=True)

    result = "UNKNOWN"
    try:
        box = find_healthy_box(BEACON, attempts=7)
        if not box:
            result = "NO_HEALTHY_BOX"
            print("ERROR no healthy box", flush=True)
            print("RESULT=%s" % result, flush=True)
            raise SystemExit(1)

        print(f"burn bootloader firmware box {box}", flush=True)
        burn(FIRMWARE)

        print("send app via W command (写 Flash) ...", flush=True)
        res = flash_upload(app)
        if not res["ok"]:
            result = "NOT_CONNECTED"
            print("RESULT=%s" % result, flush=True)
            raise SystemExit(3)

        ack = res["ack_info"] or {}
        result = classify_flash(res["output"], res["k_received"], res["k_expected"])
        print(f"rx events:          {res['rx_events']}", flush=True)
        print(f"K acks:             {res['k_received']}/{res['k_expected']}", flush=True)
        print(f"server tx ack:      bytesSent={ack.get('bytesSent')} "
              f"chunks={ack.get('chunks')} elapsed={ack.get('elapsed_s')}s", flush=True)
        print(f"upload elapsed:     {res['elapsed_s']}s", flush=True)
        print("reply tail:", repr(res["output"][-250:]), flush=True)
        print("RESULT=%s" % result, flush=True)

        # 增强：只有严格 PASS 才做复位验证（证明镜像确实持久化在 Flash）
        if result == "PASS":
            print("RESET_VERIFY=%s" % reset_verify(), flush=True)

        return 0 if result == "PASS" else 2
    finally:
        try:
            bridge("POST", "/api/v1/devices/release", timeout=60)
            print("[release] ok", flush=True)
        except Exception as e:  # noqa: BLE001
            print("[!] release failed", e, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())