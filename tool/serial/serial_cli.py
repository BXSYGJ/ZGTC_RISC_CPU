#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZGTС 本地串口 CLI（盘古 100Pro+ / PG2L100H）

用途：本机 COM 口调试与后续串口烧录的通用工具。
默认端口自动选板载 CP2102（VID_10C4 / PID_EA60），即「Silicon Labs CP210x」。

用法：
  python serial_cli.py list
  python serial_cli.py monitor  [--port COM5] [--baud 115200] [--hex] [--log out.log] [--seconds 15]
  python serial_cli.py send     [--port COM5] [--baud 115200] (--text "hi" | --hex "ff 01 a5") [--expect "OK"]
  python serial_cli.py autobaud [--port COM5] [--bauds 115200,9600,57600,38400,19200] [--seconds 2]
  python serial_cli.py echo     [--port COM5] [--baud 115200]        # 交互式：键盘输入直发，回车后发送

说明：
  - 板载串口参数默认 115200 8N1（官方 2_8_uart_test 于 27MHz 下 BPS_NUM=234）。
  - 本工具只做「PC <-> 串口」，不驱动 JTAG。烧录位流请用 PDS Configuration。
"""

import argparse
import sys
import time
from datetime import datetime

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    sys.stderr.write("缺少 pyserial，请先安装：python -m pip install pyserial\n")
    sys.exit(2)

CP2102_VID = 0x10C4
CP2102_PID = 0xEA60
DEFAULT_BAUD = 115200


def _out(text=""):
    sys.stdout.write(text)
    sys.stdout.flush()


def detect_port(prefer=CP2102_VID):
    """自动挑选端口：优先 CP210x，其次任意可用串口。"""
    ports = list(list_ports.comports())
    for p in ports:
        if p.vid == CP2102_VID and p.pid == CP2102_PID:
            return p.device
    if ports:
        return ports[0].device
    return None


def resolve_port(arg):
    port = arg or detect_port()
    if not port:
        sys.stderr.write("未找到串口，请插好 USB 并用 `serial_cli.py list` 查看。\n")
        sys.exit(1)
    return port


def cmd_list(_args):
    ports = list(list_ports.comports())
    if not ports:
        _out("(无串口设备)\n")
        return 0
    _out(f"{'PORT':<7} {'VID:PID':<10} {'DESC':<40} MANUFACTURER\n")
    for p in ports:
        vidpid = f"{p.vid:04X}:{p.pid:04X}" if p.vid is not None else "-"
        tag = "  <-- CP210x(板载串口)" if (p.vid == CP2102_VID and p.pid == CP2102_PID) else ""
        _out(f"{p.device:<7} {vidpid:<10} {str(p.description):<40} {p.manufacturer}{tag}\n")
    return 0


def open_port(port, baud):
    return serial.Serial(port=port, baudrate=baud, bytesize=8, parity="N",
                         stopbits=1, timeout=0.1)


def cmd_monitor(args):
    port = resolve_port(args.port)
    rx = 0
    logf = open(args.log, "ab") if args.log else None
    _out(f"[monitor] {port} @ {args.baud} 8N1  (Ctrl-C 退出"
         + (f", 日志 {args.log}" if args.log else "") + ")\n")
    deadline = time.time() + args.seconds if args.seconds else None
    try:
        with open_port(port, args.baud) as ser:
            pending = bytearray()
            while True:
                if deadline and time.time() > deadline:
                    _out(f"\n[monitor] 到时退出，共收 {rx} 字节\n")
                    break
                data = ser.read(256)
                if data:
                    rx += len(data)
                    if logf:
                        logf.write(data)
                        logf.flush()
                    if args.hex:
                        _out(f"{datetime.now():%H:%M:%S.%f}"[:-3] + " RX " +
                             " ".join(f"{b:02X}" for b in data) + "\n")
                    else:
                        pending += data
                        while b"\n" in pending:
                            line, _, rest = pending.partition(b"\n")
                            pending = bytearray(rest)
                            text = line.decode("utf-8", "replace").rstrip("\r")
                            _out(f"{datetime.now():%H:%M:%S} | {text}\n")
                        if len(pending) > 256:  # 没有换行也吐出，避免长时间不显示
                            _out(f"{datetime.now():%H:%M:%S} | "
                                 + pending.decode("utf-8", "replace") + "\n")
                            pending = bytearray()
    except KeyboardInterrupt:
        _out(f"\n[monitor] 中断，共收 {rx} 字节\n")
    finally:
        if logf:
            logf.close()
    return 0


def _parse_hex(s):
    return bytes.fromhex(s.replace(",", " ").replace("0x", " "))


def cmd_send(args):
    port = resolve_port(args.port)
    if args.hex:
        payload = _parse_hex(args.hex)
    elif args.text is not None:
        payload = args.text.encode("utf-8")
    else:
        sys.stderr.write("需要 --text 或 --hex\n")
        return 2
    with open_port(port, args.baud) as ser:
        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()
        _out(f"[send] {port} @ {args.baud} 已发 {len(payload)} 字节: "
             + " ".join(f"{b:02X}" for b in payload) + "\n")
        if args.expect:
            t0 = time.time()
            buf = bytearray()
            while time.time() - t0 < args.timeout:
                data = ser.read(256)
                if data:
                    buf += data
                    if args.expect.encode() in buf:
                        _out(f"[send] 命中期望串 {args.expect!r}: "
                             + buf.decode("utf-8", "replace") + "\n")
                        return 0
            _out(f"[send] {args.timeout}s 内未见 {args.expect!r}，收到: "
                 + buf.decode("utf-8", "replace") + "\n")
            return 1
    return 0


def cmd_autobaud(args):
    port = resolve_port(args.port)
    bauds = [int(b) for b in args.bauds.split(",")]
    best = (None, -1.0, b"")
    for baud in bauds:
        got = bytearray()
        try:
            with open_port(port, baud) as ser:
                t0 = time.time()
                while time.time() - t0 < args.seconds:
                    got += ser.read(4096)
        except serial.SerialException as e:
            _out(f"[autobaud] {baud:<7} 打开失败: {e}\n")
            continue
        printable = sum(1 for b in got if 32 <= b < 127 or b in (9, 10, 13))
        score = printable / len(got) if got else 0.0
        sample = bytes(got[:60]).decode("latin-1")
        _out(f"[autobaud] {baud:<7} 收 {len(got):>5} 字节, 可打印率 {score:5.1%}  样本: {sample!r}\n")
        if len(got) and score > best[1]:
            best = (baud, score, bytes(got[:120]))
    if best[0] is not None:
        _out(f"[autobaud] 最可能波特率 = {best[0]} (可打印率 {best[1]:.1%})\n")
    else:
        _out("[autobaud] 未收到数据：可能没有含 UART 的设计在运行。\n")
    return 0


def _zboot_wait_console(ser, wait_s):
    """Wait until the board is sitting at the ZBOOT '>' prompt.

    The console only prints '>' after it processes a byte, so a freshly
    opened port sees nothing. Probe with '?': the bootloader answers with
    its help text; a running application echoes the byte instead.
    Also absorbs a possible in-flight receive_image idle timeout (~4.4 s
    at 27 MHz) left over from an aborted upload.
    Returns True when the console answered with its help text."""
    deadline = time.time() + wait_s
    buf = bytearray()
    while time.time() < deadline:
        data = ser.read(256)
        if data:
            buf += data
            if b">" in buf or b"load+run" in buf:
                return True
        else:
            # nothing arriving: either idle console or a stuck receive_image
            if time.time() > deadline - wait_s + 1.0:
                ser.write(b"?")
                ser.flush()
                t0 = time.time()
                while time.time() - t0 < 2.0:
                    buf += ser.read(256)
                    if b"load+run" in buf:
                        return True
                    if buf and buf[0:1] == b"?":
                        return False   # echoed: an application is running
    return b"load+run" in buf


def cmd_load(args):
    """ZBOOT 'R' protocol upload: send 'R', 4-byte LE length, raw image.
    The bootloader acks every 256 bytes with 'K' and prints RUN before jumping
    to 0x1000. Host pacing follows the real drain rate via those acks.
    Bytes that arrive after the last expected ack (the RUN banner and the
    application's own output) are carried into the tail phase, not dropped."""
    port = resolve_port(args.port)
    with open(args.file, "rb") as f:
        image = f.read()
    if not image:
        sys.stderr.write("图像为空\n")
        return 2
    if len(image) > 0xF000:
        sys.stderr.write(f"图像 {len(image)} 字节超过 60 KB 应用区\n")
        return 2
    _out(f"[load] {port} @ {args.baud} 8N1, 镜像 {len(image)} 字节 ({args.file})\n")
    with open_port(port, args.baud) as ser:
        ser.reset_input_buffer()
        if args.no_prompt:
            _out("[load] --no-prompt：直接发送（请确认板子在 ZBOOT 控制台）\n")
        else:
            if not _zboot_wait_console(ser, args.prompt_timeout):
                _out("[load] 板子不在 ZBOOT 控制台（可能在跑应用）：按 KEY0 或重新上电后重试，"
                     "或确认状态后用 --no-prompt 强制发送\n")
                return 1
            _out("[load] 已确认板子在 ZBOOT 控制台\n")
        ser.write(b"R")
        ser.flush()
        ser.write(len(image).to_bytes(4, "little"))
        ser.flush()
        sent = 0
        acks = 0
        carry = bytearray()   # bytes received past the last expected ack
        while sent < len(image):
            chunk = image[sent:sent + 256]
            ser.write(chunk)
            ser.flush()
            sent += len(chunk)
            # wait for the 'K' ack covering this block before sending more
            while acks * 256 < sent:
                if carry:
                    data = bytes(carry)
                    carry.clear()
                else:
                    data = ser.read(64)
                    if not data:
                        continue
                if args.trace:
                    _out("[trace] RX " + " ".join(f"{b:02X}" for b in data) + "\n")
                i = 0
                while i < len(data) and acks * 256 < sent:
                    b = data[i]
                    i += 1
                    if b == 0x4B:          # 'K' ack
                        acks += 1
                    elif b in (0x0A, 0x0D):
                        pass
                    elif b == 0x3E:        # '>': console left receive mode
                        _out("[load] 板子退出接收模式（可能空闲超时），请重新开始\n")
                        return 1
                    elif b in (0x45, 0x52, 0x4E):  # 'E','R','N' of ERR text
                        _out(f"[load] 板子返回协议文本（字节 0x{b:02X}），请检查板子状态\n")
                        return 1
                    else:
                        _out(f"[load] 意外字节 0x{b:02X}（可能协议不同步，已停止）\n")
                        return 1
                carry += data[i:]         # keep RUN/HELLO text for the tail
        t0 = time.time()
        tail = bytearray(carry)
        while time.time() - t0 < args.timeout:
            if b"RUN" in tail:
                _out(f"[load] 上传完成，板子已启动应用: {bytes(tail).decode('latin-1').strip()!r}\n")
                return 0
            data = ser.read(256)
            if data:
                tail += data
        if b"RUN" in tail:
            _out(f"[load] 上传完成，板子已启动应用: {bytes(tail).decode('latin-1').strip()!r}\n")
            return 0
        _out(f"[load] 未见 RUN 响应，收到: {bytes(tail).decode('latin-1').strip()!r}\n")
        return 1


def cmd_echo(args):
    """交互式：收到的原样打印（行缓冲），键盘输入按回车整行发送，ESC 退出。"""
    port = resolve_port(args.port)
    try:
        import msvcrt
    except ImportError:
        sys.stderr.write("echo 仅支持 Windows（依赖 msvcrt）。用 monitor + send 代替。\n")
        return 2
    _out(f"[echo] {port} @ {args.baud} 8N1 —— 输入整行按回车发送，ESC 退出。\n")
    line = []
    with open_port(port, args.baud) as ser:
        while True:
            data = ser.read(256)
            if data:
                _out(data.decode("utf-8", "replace"))
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == "\x1b":  # ESC
                    _out("\n[echo] 退出\n")
                    return 0
                if ch in ("\r", "\n"):
                    payload = ("".join(line) + "\n").encode("utf-8")
                    ser.write(payload)
                    ser.flush()
                    _out(f"\n>> {''.join(line)}\n")
                    line = []
                elif ch == "\x08":  # backspace
                    if line:
                        line.pop()
                else:
                    line.append(ch)
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(prog="serial_cli.py", description="ZGTС 本地串口 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列举串口").set_defaults(func=cmd_list)

    p = sub.add_parser("monitor", help="监听串口输出")
    p.add_argument("--port"); p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--hex", action="store_true", help="以十六进制显示")
    p.add_argument("--log", help="把原始字节追加写入文件")
    p.add_argument("--seconds", type=float, default=0, help="N 秒后退出（0=一直监听）")
    p.set_defaults(func=cmd_monitor)

    p = sub.add_parser("send", help="发送数据")
    p.add_argument("--port"); p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--text"); p.add_argument("--hex", help="如 'ff 01 a5'")
    p.add_argument("--expect", help="等待出现该串")
    p.add_argument("--timeout", type=float, default=3.0)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("autobaud", help="自动探测波特率")
    p.add_argument("--port"); p.add_argument("--bauds", default="115200,9600,57600,38400,19200")
    p.add_argument("--seconds", type=float, default=2.0)
    p.set_defaults(func=cmd_autobaud)

    p = sub.add_parser("load", help="ZBOOT 'R' 协议上传应用镜像并启动")
    p.add_argument("file", help="应用二进制镜像（.bin，链接于 0x1000）")
    p.add_argument("--port"); p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.add_argument("--timeout", type=float, default=10.0, help="等待 RUN 响应的秒数")
    p.add_argument("--prompt-timeout", type=float, default=5.0, help="等待 '>' 提示符的秒数")
    p.add_argument("--no-prompt", action="store_true", help="不等待提示符直接发 R（已知板子在 ZBOOT 时用）")
    p.add_argument("--trace", action="store_true", help="打印所有收到的字节（调试协议同步）")
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("echo", help="交互式收发")
    p.add_argument("--port"); p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    p.set_defaults(func=cmd_echo)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
