#!/usr/bin/env python3
"""Wrap a raw RV32 application binary into the bootloader flash image.

Flash layout used by the bootloader at sector base 0:
  bytes 0..3   magic  'R','F','C','P'
  bytes 4..7   payload length, little-endian
  bytes 8..    payload (loaded at 0x1000 in BRAM)

Usage:  python mkflash.py app.bin app.img
"""
import sys
from pathlib import Path

MAGIC = b"RFCP"


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: mkflash.py app.bin app.img\n")
        sys.exit(2)
    payload = Path(sys.argv[1]).read_bytes()
    if not payload:
        sys.stderr.write("empty application\n")
        sys.exit(1)
    image = MAGIC + len(payload).to_bytes(4, "little") + payload
    Path(sys.argv[2]).write_bytes(image)
    print(f"flash image: {len(image)} bytes ({len(payload)} byte payload)")


if __name__ == "__main__":
    main()
