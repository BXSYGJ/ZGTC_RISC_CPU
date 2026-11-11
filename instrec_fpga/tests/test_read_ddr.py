"""Tests for the formal read-back module (scripts/read_ddr.py).

The reader is a plug-in ``(cmd_addr) -> 256-byte frame``, so these tests drive
it from the behavioural memory model and diff the whole production path
byte-for-byte -- no board, no serial port.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "scripts"))

import ddr3_mem_model as mm                     # noqa: E402
import read_ddr as rd                           # noqa: E402
from ddr3_layout import BYTE_ADDR_UNIT, HW_ADDR_UNIT  # noqa: E402


def _pcm_pages(npages=8256):
    return [struct.pack("<16h", *[((p * 16 + s) % 16384) + 1
                                  for s in range(16)])
            for p in range(npages)]


def test_pcm_window_base_ping_pong():
    assert rd.pcm_win_base(0) == 0x000000
    assert rd.pcm_win_base(1) == 0x042000
    assert rd.pcm_win_base(2) == 0x000000
    assert rd.pcm_win_base(3) == 0x042000


def test_region_plan_is_page_strided():
    plan = rd.region_plan(0, rd.PCM_BYTES, HW_ADDR_UNIT)
    cmds = [c for c, _s in plan]
    # 2 pages per 256 B frame under x4 -> cmd stride 64 B
    assert cmds[0] == 0 and cmds[1] == 64 and cmds[-1] == 8256 * 32 - 64


def test_read_pcm_roundtrip_under_byte_semantics():
    pages = _pcm_pages()
    mem = mm.Ddr3PhysicalMemory(addr_unit=BYTE_ADDR_UNIT)
    mm.write_pages(mem, 0, pages)
    raw = rd.read_pcm(mem.read_frame, 0, BYTE_ADDR_UNIT)
    assert raw == b"".join(pages)
    samples = struct.unpack("<%dh" % rd.PCM_SAMPLES, raw)
    assert samples[0] == 1 and samples[1] == 2


def test_read_pcm_reconstruction_under_measured_unit():
    # x4: the raw frames alias; the de-stride must still recover every page.
    pages = _pcm_pages()
    mem = mm.Ddr3PhysicalMemory(addr_unit=HW_ADDR_UNIT)
    mm.write_pages(mem, 0, pages)
    raw = rd.read_pcm(mem.read_frame, 0, HW_ADDR_UNIT)
    assert raw == b"".join(pages)


def test_read_feat_deinterleaves_low_byte_under_both_units():
    elements = [(e * 7919) & 0xFF for e in range(rd.FEAT_ELEMENTS)]
    slots = mm.feat_slots(elements)
    npages = rd.FEAT_BYTES // 32
    pages = [slots[p * 32:(p + 1) * 32] for p in range(npages)]
    for unit in (HW_ADDR_UNIT, BYTE_ADDR_UNIT):
        mem = mm.Ddr3PhysicalMemory(addr_unit=unit)
        mm.write_pages(mem, rd.FEAT_BASE, pages)
        assert rd.read_feat(mem.read_frame, unit) == bytes(elements)


def test_repeated_readback_of_locked_window_is_identical():
    pages = _pcm_pages(1024)
    mem = mm.Ddr3PhysicalMemory(addr_unit=HW_ADDR_UNIT)
    mm.write_pages(mem, 0, pages)
    first = rd.read_pcm(mem.read_frame, 0, HW_ADDR_UNIT)
    for _ in range(3):
        assert rd.read_pcm(mem.read_frame, 0, HW_ADDR_UNIT) == first
