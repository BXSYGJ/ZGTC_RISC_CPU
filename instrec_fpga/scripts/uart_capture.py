#!/usr/bin/env python3
"""Capture UART bytes from the board (T-M1-07 prerequisite).

Usage:
  python scripts/uart_capture.py --port COM5 --baud 115200 --seconds 20 --out build/uart.log
  python scripts/uart_capture.py --port COM5 --seconds 20 --hex

Default output is a UTF-8 text dump with non-printable bytes escaped.
Exit code 0 if the port opened, 2 if it could not be opened.
"""
import argparse
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--seconds', type=float, default=10.0)
    ap.add_argument('--out')
    ap.add_argument('--hex', action='store_true')
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        print('pyserial not installed: pip install pyserial', file=sys.stderr)
        return 2

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:
        print(f'cannot open {args.port}: {exc}', file=sys.stderr)
        return 2

    chunks = []
    deadline = time.time() + args.seconds
    try:
        while time.time() < deadline:
            data = ser.read(4096)
            if data:
                chunks.append(data)
    finally:
        ser.close()

    raw = b''.join(chunks)
    if args.hex:
        text = raw.hex()
        text = ' '.join(text[i:i + 2] for i in range(0, len(text), 2))
    else:
        text = ''.join(chr(b) if 32 <= b < 127 or b in (10, 13, 9) else f'\\x{b:02x}'
                       for b in raw)

    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)
    print(text)
    print(f'[captured {len(raw)} byte(s)]', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())