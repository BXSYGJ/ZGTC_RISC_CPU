"""Unit tests for the DDR3 command-address layout conversion (scripts/ddr3_layout.py).

The layout module is the single source of truth for the measured contract
``physical = ADDR_UNIT * cmd_addr + 32 * beat``.  These tests lock the two
supported address units (4 = measured on board, 1 = documented byte semantics)
and the diag frame-plan / destride conversion used by every host read-back.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ddr3_layout as L   # noqa: E402


def _page(p):
    samples = [((p * 16 + s) % 65536) - 32768 for s in range(16)]
    return struct.pack("<16h", *samples)


def test_physical_scaling_matches_the_measured_probe():
    # probe build/probe_addr_unit.py: read(32)[0:128] == read(0)[128:256].
    assert L.physical(0, 4) == 0
    assert L.physical(32, 4) == 128
    assert L.physical(64, 4) == 256
    assert L.physical(32, 1) == 32


def test_pages_per_frame():
    assert L.pages_per_frame(4) == 2   # 256 B frame = 2 x 128 B pages
    assert L.pages_per_frame(1) == 8   # 256 B frame = 8 x 32 B pages


def test_frame_plan_cmd_addresses_are_page_strided():
    for unit in (4, 1):
        plan = L.frame_plan(0, 8256, unit)
        ppf = L.pages_per_frame(unit)
        cmds = [cmd for cmd, _spans in plan]
        assert cmds == [p * L.PAGE_BYTES for p in range(0, 8256, ppf)]
        for cmd, spans in plan:
            # spans select whole pages, one per page inside the frame
            assert [off for off, _n in spans] == [j * L.PAGE_BYTES * unit
                                                  for j in range(ppf)]
            assert all(n == L.PAGE_BYTES for _off, n in spans)


def test_destride_places_spans_at_the_measured_offsets():
    # unit=4: page 0 at payload[0:32], page 1 at payload[128:160].
    plan = L.frame_plan(0, 2, 4)
    assert plan == [(0, [(0, 32), (128, 32)])]
    f0 = bytearray([0xA5]) * L.FRAME_BYTES
    f0[0:32] = _page(0)
    f0[128:160] = _page(1)
    assert L.destride([bytes(f0)], plan) == _page(0) + _page(1)


def test_destride_under_byte_semantics_is_contiguous():
    plan = L.frame_plan(0, 8, 1)
    assert plan == [(0, [(j * 32, 32) for j in range(8)])]
    f0 = bytes(range(256))
    assert L.destride([f0], plan) == f0


def test_destride_roundtrip_over_a_full_window_under_both_units():
    npages = 8256
    pages = [struct.pack("<16h", *[(p * 16 + s) % 2048 for s in range(16)])
             for p in range(npages)]
    for unit in (4, 1):
        plan = L.frame_plan(0, npages, unit)
        frames = []
        for cmd, spans in plan:
            frame = bytearray([0xA5]) * L.FRAME_BYTES
            for page_index in range(len(spans)):
                # which global page lands at this span, given the cmd stride
                global_page = cmd // L.PAGE_BYTES + page_index
                off, _n = spans[page_index]
                frame[off:off + L.PAGE_BYTES] = pages[global_page]
            frames.append(bytes(frame))
        assert L.destride(frames, plan) == b"".join(pages)


def test_feat_slot_unpack_drops_high_byte():
    # {8'h00, feat_data} expands little-endian: feat_data first, 0x00 second.
    raw = bytes((10, 0, 20, 0, 30, 0))
    assert L.feat_slots_to_bytes(raw) == bytes((10, 20, 30))


def test_pages_for_and_frame_count():
    assert L.pages_for(264192) == 8256
    assert L.frame_count(8256, 4) == 4128
    assert L.frame_count(8256, 1) == 1032
