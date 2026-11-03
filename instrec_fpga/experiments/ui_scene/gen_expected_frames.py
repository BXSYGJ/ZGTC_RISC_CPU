#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_expected_frames.py - software reference renderer for tb_ui_scene.

Implements the UI Scene ABI v0 rendering semantics independently of the RTL
(same glyph ROM, same geometry rules) and emits, into build/sim/ui_scene/:

    frame_init.hex   640x360 all-black reference frame (pre-commit state)
    frame_a.hex      reference frame for scene A
    frame_b.hex      reference frame for scene B
    scene_a_desc.hex 256 descriptor words (32 slots x 8 words) of scene A
    scene_a_glyph.hex 512 glyph id bytes of scene A
    scene_b_desc.hex / scene_b_glyph.hex   same for scene B

The scene tables are the single source of truth: tb_ui_scene.sv loads the
descriptor/glyph hex files and drives them through the CPU write port, so
the RTL and this reference model always see identical scene data.

Semantics (must match ui_scene_render.v bit-exactly):
  * Priority: the lowest slot index whose rectangle covers the pixel wins;
    inside the winner, non-ink pixels (blank glyph dots, the unfilled part
    of a bar) are black.  This is equivalent to painting slots from the
    highest index down with each rectangle being opaque.
  * TEXT: 16x32 px per character, glyph id = glyph_ram[(gptr + char_idx)
    & 511] & 0x7F, dot bit = bit (15 - dx%16) of ROM word
    (gid * 32 + dy%32); only char_idx < value renders ink.
  * BAR: ink where dx * 1000 < value * w (32-bit arithmetic, no overflow
    for the ABI ranges).
  * RECT: full rectangle ink.

Usage:
    python experiments/ui_scene/gen_expected_frames.py [--out DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from gen_glyph_hex import glyph_rows  # noqa: E402  (same-directory module)

IMG_W = 640
IMG_H = 360

# Scene slot types (UI Scene ABI v0).
TYPE_HIDDEN = 0
TYPE_TEXT = 1
TYPE_BAR = 2
TYPE_RECT = 3


def encode_slot(slot: dict) -> list[int]:
    """Encode one slot dict into the 8 ABI descriptor words."""
    typ = slot.get("type", TYPE_HIDDEN)
    flags = slot.get("flags", 0)
    visible = slot.get("visible", 1 if typ != TYPE_HIDDEN else 0)
    return [
        (typ & 0xFF) | ((flags & 0xFF) << 8) | ((visible & 1) << 16),
        (slot["x"] & 0xFFF) | ((slot["y"] & 0xFFF) << 12),
        (slot["w"] & 0xFFF) | ((slot["h"] & 0xFFF) << 12),
        slot["color"] & 0xFFFFFF,
        slot.get("value", 0) & 0xFFFF,
        slot.get("gptr", 0) & 0x1FF,
        0,
        0,
    ]


def encode_scene(slots: dict[int, dict]) -> list[int]:
    """Encode a {slot_index: slot} mapping into 256 descriptor words."""
    words: list[int] = []
    for idx in range(32):
        if idx in slots:
            words.extend(encode_slot(slots[idx]))
        else:
            words.extend(encode_slot({"type": TYPE_HIDDEN, "x": 0, "y": 0,
                                      "w": 0, "h": 0, "color": 0}))
    assert len(words) == 256
    return words


def encode_glyphs(layout: dict[int, bytes]) -> list[int]:
    """Pack {offset: glyph id bytes} into the 512-entry glyph sequence."""
    glyphs = [0] * 512
    for offset, data in layout.items():
        assert offset + len(data) <= 512, "glyph layout overflows the RAM"
        for i, ch in enumerate(data):
            glyphs[offset + i] = ch & 0xFF
    return glyphs


# --------------------------------------------------------------------------
# Scene definitions (shared with the TB through the generated hex tables).
# --------------------------------------------------------------------------
SCENE_A_SLOTS = {
    0: dict(type=TYPE_TEXT, x=16, y=16, w=176, h=32, color=0xFFFFFF,
            value=11, gptr=0),                     # "INSTREC NPU"
    1: dict(type=TYPE_TEXT, x=16, y=56, w=240, h=32, color=0x36D6C5,
            value=15, gptr=32),                    # "UI SCENE ABI V0"
    2: dict(type=TYPE_TEXT, x=16, y=96, w=224, h=32, color=0xF2BA59,
            value=14, gptr=96),                    # "640X360 CANVAS"
    3: dict(type=TYPE_BAR, x=64, y=280, w=512, h=24, color=0x36D6C5,
            value=500, gptr=0),                    # 50% bar
}

SCENE_A_GLYPHS = encode_glyphs({
    0: b"INSTREC NPU",
    32: b"UI SCENE ABI V0",
    96: b"640X360 CANVAS",
})

SCENE_B_SLOTS = {
    4: dict(type=TYPE_RECT, x=0, y=0, w=640, h=60, color=0x0B1020),
    0: dict(type=TYPE_TEXT, x=16, y=14, w=112, h=32, color=0xFFFFFF,
            value=7, gptr=0),                      # "SCENE B"
    1: dict(type=TYPE_TEXT, x=16, y=120, w=192, h=32, color=0xEAF0F7,
            value=12, gptr=32),                    # "BANK SWAP OK"
    2: dict(type=TYPE_BAR, x=64, y=250, w=512, h=24, color=0xF2BA59,
            value=250, gptr=0),                    # 25% bar
    3: dict(type=TYPE_BAR, x=64, y=300, w=512, h=24, color=0x36D6C5,
            value=875, gptr=0),                    # 87.5% bar
}

SCENE_B_GLYPHS = encode_glyphs({
    0: b"SCENE B",
    32: b"BANK SWAP OK",
})


# --------------------------------------------------------------------------
# Reference renderer.
# --------------------------------------------------------------------------
GLYPH_ROM = [glyph_rows(code) for code in range(128)]


def render_frame(desc_words: list[int], glyph_ids: list[int]) -> list[int]:
    """Render one 640x360 frame (row-major RGB888 words)."""
    frame = [0] * (IMG_W * IMG_H)

    # Paint from the highest slot index down; lower indices overwrite, so
    # the lowest covering slot ends up visible (opaque-rectangle model).
    for slot in range(31, -1, -1):
        base = slot * 8
        w0 = desc_words[base + 0]
        w1 = desc_words[base + 1]
        w2 = desc_words[base + 2]
        w3 = desc_words[base + 3]
        w4 = desc_words[base + 4]
        w5 = desc_words[base + 5]
        typ = w0 & 0xFF
        visible = (w0 >> 16) & 1
        if not visible or typ == TYPE_HIDDEN:
            continue
        x0 = w1 & 0xFFF
        y0 = (w1 >> 12) & 0xFFF
        sw = w2 & 0xFFF
        sh = (w2 >> 12) & 0xFFF
        color = w3 & 0xFFFFFF
        value = w4 & 0xFFFF
        gptr = w5 & 0x1FF

        y_lo, y_hi = y0, min(y0 + sh, IMG_H)
        x_lo, x_hi = x0, min(x0 + sw, IMG_W)
        for py in range(y_lo, y_hi):
            dy = py - y0
            row_off = py * IMG_W
            for px in range(x_lo, x_hi):
                dx = px - x0
                ink = False
                if typ == TYPE_RECT:
                    ink = True
                elif typ == TYPE_BAR:
                    ink = (dx * 1000) < (value * sw)
                elif typ == TYPE_TEXT:
                    char_idx = dx >> 4
                    if char_idx < value:
                        gid = glyph_ids[(gptr + char_idx) & 0x1FF] & 0x7F
                        bits = GLYPH_ROM[gid][dy & 0x1F]
                        ink = (bits >> (15 - (dx & 0xF))) & 1 == 1
                frame[row_off + px] = color if ink else 0
    return frame


def write_hex(path: Path, values, digits: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        for v in values:
            handle.write(("%0" + str(digits) + "X\n") % (int(v) & ((1 << (4 * digits)) - 1)))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "build" / "sim" / "ui_scene"),
                        help="output directory (default: %(default)s)")
    args = parser.parse_args(argv)
    out = Path(args.out)

    desc_a = encode_scene(SCENE_A_SLOTS)
    desc_b = encode_scene(SCENE_B_SLOTS)
    glyphs_a = SCENE_A_GLYPHS
    glyphs_b = SCENE_B_GLYPHS

    frame_a = render_frame(desc_a, glyphs_a)
    frame_b = render_frame(desc_b, glyphs_b)
    frame_init = [0] * (IMG_W * IMG_H)

    write_hex(out / "scene_a_desc.hex", desc_a, 8)
    write_hex(out / "scene_a_glyph.hex", glyphs_a, 2)
    write_hex(out / "scene_b_desc.hex", desc_b, 8)
    write_hex(out / "scene_b_glyph.hex", glyphs_b, 2)
    write_hex(out / "frame_init.hex", frame_init, 6)
    write_hex(out / "frame_a.hex", frame_a, 6)
    write_hex(out / "frame_b.hex", frame_b, 6)

    diff = sum(1 for a, b in zip(frame_a, frame_b) if a != b)
    inked = sum(1 for v in frame_a if v) + sum(1 for v in frame_b if v)
    if diff == 0:
        print("ERROR: reference frames A and B are identical")
        return 1
    print("wrote %s: frame_a ink=%d, frame_b ink=%d, A-vs-B diff=%d pixels"
          % (out, sum(1 for v in frame_a if v), sum(1 for v in frame_b if v),
             diff))
    print("unused ink check: %d inked pixels across both frames" % inked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
