#!/usr/bin/env python3
"""Send an application to the SoC bootloader over UART.

Default behaviour writes the application to the on-board SPI flash and boots
it ('W'); pass --ram to load-and-run directly without touching flash ('R'),
which is handy while iterating because it skips the flash erase/program delay.

With --port the payload is sent over pyserial to a local/board UART. Without
--port the exact byte stream is written to a file so it can be replayed later
(for example when the remote lab exposes the UART only through its web
console).

Usage examples:
  python burn.py app.bin --port COM7
  python burn.py app.bin --ram   --port COM7
  python burn.py app.bin              # writes app.uart.dat instead
"""
import argparse
import sys
import time
from pathlib import Path

U32 = lambda v: int(v).to_bytes(4, "little")


def build_command(payload, ram):
    command = b"R" if ram else b"W"
    return command + U32(len(payload)) + payload


def dump_command(path, payload, ram):
    Path(path).write_bytes(build_command(payload, ram))
    print(f"wrote {Path(path).name} ({len(payload) + 5} bytes): "
          f"prefix {b'R' if ram else b'W'}")


def serial_send(port, payload, ram, baud, wait, banner_timeout):
    import serial
    with serial.Serial(port, baud, timeout=0.5) as link:
        link.reset_input_buffer()
        start = time.time()
        text = b""
        while time.time() - start < banner_timeout:
            chunk = link.read(64)
            if chunk:
                text += chunk
                if b"ZBOOT" in text:
                    break
        # Report whatever the bootloader already printed (debug/confirmation).
        data = build_command(payload, ram)
        link.write(data)
        end = time.time() + wait
        reply = b""
        while time.time() < end:
            chunk = link.read(256)
            if chunk:
                reply += chunk
        printable = "".join(chr(c) if 32 <= c < 127 else "." for c in reply)
        print(f"reply: {printable!r}")
        if b"FLASHED" in reply or b"RUN" in reply or b"ERASED" in reply:
            return 0
        return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--port", default="")
    parser.add_argument("--ram", action="store_true",
                        help="load and run from RAM instead of writing flash")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--wait", type=float, default=3.0)
    parser.add_argument("--out", default="app.uart.dat")
    args = parser.parse_args()

    if not args.binary.is_file():
        sys.stderr.write(f"{args.binary} does not exist\n")
        sys.exit(2)
    payload = args.binary.read_bytes()
    if len(payload) > 0xF000:
        sys.stderr.write("application exceeds the 60 KB BRAM region\n")
        sys.exit(2)

    if args.port:
        try:
            sys.exit(serial_send(args.port, payload, args.ram,
                                 args.baud, args.wait, banner_timeout=2.0))
        except Exception as exc:  # pyserial / IO errors
            sys.stderr.write(f"serial error: {exc}\n")
            sys.exit(1)
    else:
        dump_command(args.out, payload, args.ram)


if __name__ == "__main__":
    main()
