#!/usr/bin/env python3
"""Capture UART bytes from the board and optionally parse layer-export frames.

Usage:
  python scripts/uart_capture.py --port COM5 --seconds 20 --out build/uart.log
  python scripts/uart_capture.py --port COM5 --seconds 20 --hex
  python scripts/uart_capture.py --port COM5 --seconds 30 --frames --out-dir reports/m2_frames
  python scripts/uart_capture.py --port COM5 --seconds 30 --frames --layer 0x06

Default output is a UTF-8 text dump with non-printable bytes escaped.
With --frames the raw stream is parsed as design.md 9.2 frames
(AA | layer_id | seq | len | payload | crc16); each observed layer is
reassembled and saved as .npy when --out-dir is given.
Exit code 0 if the port opened, 2 if it could not be opened.
"""
import argparse
import sys
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', default='COM5')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--seconds', type=float, default=10.0)
    ap.add_argument('--out')
    ap.add_argument('--hex', action='store_true')
    ap.add_argument('--frames', action='store_true')
    ap.add_argument('--out-dir')
    ap.add_argument('--layer')
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

    if args.frames:
        import uart_frames as uf

        frames = uf.parse_frames(raw)
        counts = {}
        for lid, _seq, payload in frames:
            counts[lid] = counts.get(lid, 0) + len(payload)
        print(f'[frames {len(frames)}, bytes {len(raw)}]', file=sys.stderr)
        for lid in sorted(counts):
            name = uf.LAYER_NAMES.get(lid & 0x7F, '?')
            flag = ' (sampled)' if lid & 0x80 else ''
            print(f'  layer 0x{lid:02x} {name}{flag}: {counts[lid]} bytes')

        wanted = None
        if args.layer:
            wanted = int(args.layer, 0)
        if args.out_dir:
            import numpy as np

            out_dir = Path(args.out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            for lid in sorted(counts):
                if wanted is not None and lid != wanted:
                    continue
                try:
                    arr = uf.reassemble(frames, lid)
                except ValueError as exc:
                    print(f'  layer 0x{lid:02x}: {exc}', file=sys.stderr)
                    continue
                path = out_dir / f'layer_{lid:02x}.npy'
                np.save(path, arr)
                print(f'  saved {path} {arr.shape} {arr.dtype}')
        print(f'[captured {len(raw)} byte(s)]', file=sys.stderr)
        return 0

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