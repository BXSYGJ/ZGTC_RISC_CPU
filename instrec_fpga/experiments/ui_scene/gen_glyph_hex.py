#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_glyph_hex.py - 16x32 glyph ROM generator for the ui_scene experiment.

Generates src/ui_scene/glyph16x32.hex: 128 ASCII characters, 32 scanlines
each, one 16-bit word per line (MSB = leftmost pixel), 4096 words total.

Glyph shape: a classic 5x7 dot-matrix font, block-scaled by 3 in X and 4 in
Y (15x28 ink area), centred in the 16x32 cell (2 blank rows top and bottom,
1 blank column on the right).  Control characters (0x00..0x1F, 0x7F) render
as a blank cell.  The generator is deterministic and dependency-free so the
hex file can always be regenerated bit-exactly.

Usage:
    python experiments/ui_scene/gen_glyph_hex.py [--out PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "src" / "ui_scene" / "glyph16x32.hex"

# Cell geometry
SCALE_X = 3
SCALE_Y = 4
X_OFF = 0            # ink columns 0..14, column 15 blank
Y_OFF = 2            # ink rows 2..29, rows 0/1/30/31 blank
GLYPH_W = 16
GLYPH_H = 32

# Classic 5x7 dot-matrix font for the printable ASCII range 0x20..0x7E.
# Each entry: 7 rows, 5 bits per row, bit4 = leftmost column.
FONT_5X7 = {
    " ": "00 00 00 00 00 00 00",
    "!": "00 04 04 04 04 00 04",
    '"': "00 0A 0A 00 00 00 00",
    "#": "00 0A 1F 0A 1F 0A 00",
    "$": "04 0F 14 0E 05 1F 04",
    "%": "18 19 02 04 08 13 03",
    "&": "08 14 14 08 15 12 0D",
    "'": "00 04 04 00 00 00 00",
    "(": "02 04 08 08 08 04 02",
    ")": "08 04 02 02 02 04 08",
    "*": "00 04 15 0E 15 04 00",
    "+": "00 04 04 1F 04 04 00",
    ",": "00 00 00 00 00 04 08",
    "-": "00 00 00 1F 00 00 00",
    ".": "00 00 00 00 00 0C 0C",
    "/": "00 01 02 04 08 10 00",
    "0": "0E 11 13 15 19 11 0E",
    "1": "04 0C 04 04 04 04 0E",
    "2": "0E 11 01 02 04 08 1F",
    "3": "1F 02 04 02 01 11 0E",
    "4": "02 06 0A 12 1F 02 02",
    "5": "1F 10 1E 01 01 11 0E",
    "6": "06 08 10 1E 11 11 0E",
    "7": "1F 01 02 04 08 08 08",
    "8": "0E 11 11 0E 11 11 0E",
    "9": "0E 11 11 0F 01 02 0C",
    ":": "00 0C 0C 00 0C 0C 00",
    ";": "00 0C 0C 00 0C 04 08",
    "<": "00 02 04 08 04 02 00",
    "=": "00 00 1F 00 1F 00 00",
    ">": "00 08 04 02 04 08 00",
    "?": "0E 11 01 02 04 00 04",
    "@": "0E 11 17 15 17 10 0E",
    "A": "0E 11 11 1F 11 11 11",
    "B": "1E 11 11 1E 11 11 1E",
    "C": "0E 11 10 10 10 11 0E",
    "D": "1C 12 11 11 11 12 1C",
    "E": "1F 10 10 1E 10 10 1F",
    "F": "1F 10 10 1E 10 10 10",
    "G": "0E 11 10 17 11 11 0F",
    "H": "11 11 11 1F 11 11 11",
    "I": "0E 04 04 04 04 04 0E",
    "J": "07 02 02 02 02 12 0C",
    "K": "11 12 14 18 14 12 11",
    "L": "10 10 10 10 10 10 1F",
    "M": "11 1B 15 15 11 11 11",
    "N": "11 19 15 13 11 11 11",
    "O": "0E 11 11 11 11 11 0E",
    "P": "1E 11 11 1E 10 10 10",
    "Q": "0E 11 11 11 15 12 0D",
    "R": "1E 11 11 1E 14 12 11",
    "S": "0F 10 10 0E 01 01 1E",
    "T": "1F 04 04 04 04 04 04",
    "U": "11 11 11 11 11 11 0E",
    "V": "11 11 11 11 11 0A 04",
    "W": "11 11 11 15 15 1B 11",
    "X": "11 11 0A 04 0A 11 11",
    "Y": "11 11 11 0A 04 04 04",
    "Z": "1F 01 02 04 08 10 1F",
    "[": "0F 08 08 08 08 08 0F",
    "\\": "00 10 08 04 02 01 00",
    "]": "0F 01 01 01 01 01 0F",
    "^": "04 0A 11 00 00 00 00",
    "_": "00 00 00 00 00 00 1F",
    "`": "08 04 00 00 00 00 00",
    "a": "00 00 0E 01 0F 11 0F",
    "b": "10 10 1E 11 11 11 1E",
    "c": "00 00 0F 10 10 10 0F",
    "d": "01 01 0F 11 11 11 0F",
    "e": "00 00 0E 11 1F 10 0E",
    "f": "06 08 08 1E 08 08 08",
    "g": "00 0F 11 11 0F 01 1E",
    "h": "10 10 1E 11 11 11 11",
    "i": "04 00 0C 04 04 04 0E",
    "j": "02 00 06 02 02 12 0C",
    "k": "10 10 12 14 18 14 12",
    "l": "0C 04 04 04 04 04 0E",
    "m": "00 00 1B 15 15 15 15",
    "n": "00 00 1E 11 11 11 11",
    "o": "00 00 0E 11 11 11 0E",
    "p": "00 1E 11 11 1E 10 10",
    "q": "00 0F 11 11 0F 01 01",
    "r": "00 00 16 09 08 08 08",
    "s": "00 00 0F 10 0E 01 1E",
    "t": "08 08 1E 08 08 08 06",
    "u": "00 00 11 11 11 11 0F",
    "v": "00 00 11 11 11 0A 04",
    "w": "00 00 11 11 11 15 0A",
    "x": "00 00 11 0A 04 0A 11",
    "y": "00 00 11 11 0F 01 0E",
    "z": "00 00 1F 02 04 08 1F",
    "{": "06 08 08 10 08 08 06",
    "|": "04 04 04 04 04 04 04",
    "}": "0C 02 02 01 02 02 0C",
    "~": "00 00 0A 15 02 00 00",
}

_FONT_CACHE: dict[int, list[int]] = {}


def font_rows(code: int) -> list[int]:
    """5x7 rows for an ASCII code; blank cell when the font has no glyph."""
    if code in _FONT_CACHE:
        return _FONT_CACHE[code]
    ch = chr(code) if 0x20 <= code <= 0x7E else None
    if ch is None or ch not in FONT_5X7:
        rows = [0] * 7
    else:
        rows = [int(tok, 16) for tok in FONT_5X7[ch].split()]
    _FONT_CACHE[code] = rows
    return rows


def glyph_rows(code: int) -> list[int]:
    """32 words (16 bit, MSB = leftmost) of one 16x32 glyph cell."""
    src = font_rows(code)
    words = []
    for row in range(GLYPH_H):
        word = 0
        dy = row - Y_OFF
        if 0 <= dy < 7 * SCALE_Y:
            src_row = src[dy // SCALE_Y]
            for sx in range(5):
                if src_row & (1 << (4 - sx)):
                    for k in range(SCALE_X):
                        word |= 1 << (15 - (sx * SCALE_X + k + X_OFF))
        words.append(word)
    return words


def build_glyph_rom() -> list[int]:
    """Flat 4096-word ROM image: addr = code * 32 + row."""
    words = []
    for code in range(128):
        words.extend(glyph_rows(code))
    return words


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="output hex path (default: %(default)s)")
    args = parser.parse_args(argv)

    rom = build_glyph_rom()
    assert len(rom) == 4096, "ROM image must hold exactly 4096 words"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="ascii", newline="\n") as handle:
        for word in rom:
            handle.write("%04X\n" % (word & 0xFFFF))

    inked = sum(1 for w in rom if w)
    print("wrote %s: %d words (128 chars x 32 rows), %d non-blank rows"
          % (out, len(rom), inked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
