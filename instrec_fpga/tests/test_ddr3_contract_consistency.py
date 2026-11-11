"""Production-path data-consistency tests under the measured DDR3 address unit.

These tests transcribe the exact RTL command geometry of the four production
masters and diff two paths byte for byte, so "they share an address space"
is never used as a substitute for actual verification:

  * audio_sink  -> single-beat (len=0) 32 B page writes, cmd stride 32 B
  * mel_engine  -> 16-beat (len=15) reads, cmd stride 512 B
  * weight_loader -> 8-beat (len=7) 256 B frame writes, cmd stride 256 B
  * wdma        -> 16-beat (len=15) reads, cmd addr +32 B per beat
  * feat export -> single-beat 32 B slot writes, cmd stride 32 B
  * diag_readback -> 8-beat (len=7) frames, cmd stride 256 B

Key conclusion locked here: under ADDR_UNIT=4 a sparse single-beat write does
NOT match a contiguous multi-beat read (the read consumes 3/4 or 1/2 physical
gap).  Only ADDR_UNIT=1 makes the two paths agree.  This is a functional bug,
not merely wasted address space.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "scripts"))

import ddr3_ctrl_model as dm            # noqa: E402
import ddr3_mem_model as mm             # noqa: E402
from ddr3_layout import HW_ADDR_UNIT, BYTE_ADDR_UNIT, PAGE_BYTES  # noqa: E402

PCM_PAGES = 8256
FEAT_SLOTS = 64 * 258                   # 16,512 uint8


def _pcm_pages(npages=PCM_PAGES):
    pages = []
    for p in range(npages):
        pages.append(struct.pack("<16h",
                                 *[((p * 16 + s) % 65536) - 32768
                                   for s in range(16)]))
    return pages


def _pcm_samples(pages):
    out = []
    for pg in pages:
        out.extend(struct.unpack("<16h", pg))
    return out


def test_audio_write_to_mel_read_matches_only_under_byte_semantics():
    # strictly positive samples so the zero-fill sentinel can never collide
    pages = [struct.pack("<16h", *[((p * 16 + s) % 16384) + 1
                                   for s in range(16)])
             for p in range(PCM_PAGES)]
    expected = _pcm_samples(pages)

    # ADDR_UNIT=4 (measured): sparse page writes vs 16-beat reads disagree.
    mem4 = mm.Ddr3PhysicalMemory(addr_unit=HW_ADDR_UNIT, fill=0x00)
    mm.write_pages(mem4, 0, pages)
    got4 = mm.mel_read_samples(mem4, 0)
    assert len(got4) == len(expected)
    assert got4 != expected
    # Only the 0-th beat of each 16-beat command aligns with a real page;
    # beats 1..15 read the 128 B physical gaps (zero fill).  The position-
    # correct samples are exactly the first 16 of every 256-sample command.
    correct = [i for i in range(len(expected)) if got4[i] == expected[i]]
    assert correct == [k * 256 + s for k in range(PCM_PAGES * 16 // 256)
                       for s in range(16)]

    # ADDR_UNIT=1 (documented byte semantics): exact recovery.
    mem1 = mm.Ddr3PhysicalMemory(addr_unit=BYTE_ADDR_UNIT, fill=0x00)
    mm.write_pages(mem1, 0, pages)
    assert mm.mel_read_samples(mem1, 0) == expected


def test_weight_upload_to_wdma_read_matches_only_under_byte_semantics():
    image = bytes((i * 2654435761) & 0xFF for i in range(4096))

    mem4 = mm.Ddr3PhysicalMemory(addr_unit=HW_ADDR_UNIT)
    mm.upload_frames(mem4, 0x100000, image)
    got4 = mm.read_contiguous(mem4, 0x100000, len(image))
    assert got4 != image

    mem1 = mm.Ddr3PhysicalMemory(addr_unit=BYTE_ADDR_UNIT)
    mm.upload_frames(mem1, 0x100000, image)
    assert mm.read_contiguous(mem1, 0x100000, len(image)) == image


def test_feat_export_is_recoverable_via_diag_destride_under_both_units():
    elements = [(e * 7919) & 0xFF for e in range(FEAT_SLOTS)]
    slots = mm.feat_slots(elements)

    for unit in (HW_ADDR_UNIT, BYTE_ADDR_UNIT):
        mem = mm.Ddr3PhysicalMemory(addr_unit=unit)
        # feat export writes 16 slots (32 B) per single-beat command
        npages = FEAT_SLOTS // 16
        pages = [slots[p * 32:(p + 1) * 32] for p in range(npages)]
        mm.write_pages(mem, 0x200000, pages)
        raw = mm.read_pages_via_diag(mem, 0x200000, npages)
        assert mm.unpack_feat(raw) == bytes(elements)


def test_repeated_readback_of_a_locked_window_is_byte_identical():
    pages = _pcm_pages(1024)
    mem = mm.Ddr3PhysicalMemory(addr_unit=HW_ADDR_UNIT)
    mm.write_pages(mem, 0, pages)
    first = mm.read_pages_via_diag(mem, 0, 1024)
    for _ in range(3):
        assert mm.read_pages_via_diag(mem, 0, 1024) == first


def test_cross_page_cross_burst_cross_window_monotonic_ramp():
    # A strictly increasing sample ramp must survive mel read under byte
    # semantics across page (32 B), burst (512 B) and window (8256 pages)
    # boundaries without dropping or reordering a single sample.
    pages = _pcm_pages()
    mem = mm.Ddr3PhysicalMemory(addr_unit=BYTE_ADDR_UNIT)
    mm.write_pages(mem, 0, pages)
    got = mm.mel_read_samples(mem, 0)
    assert got == _pcm_samples(pages)
    # adjacency check: consecutive samples differ by +1 except at int16 wrap
    for a, b in zip(got, got[1:]):
        assert (b - a) % 65536 == 1


def test_timeout_is_not_success():
    """A command that only times out must NOT look like a successful read.

    The controller still pulses `done` on abort (to avoid upstream deadlock),
    so an upper layer that keys off `done` alone would mistake an abort for a
    completed read.  The distinguishing signal is `to_abort` / `to_err`, which
    stay clear on a real read completion.
    """
    model = dm.Ddr3CtrlAxiModel()
    ip = dm.ReadyIp(aw_latency=0, w_latency=0, ar_latency=0, never=('r',))
    cmd = dm.pack_cmd(0, 0x200000, dm.BURST_LEN)
    valid = (0, 0, 0, 1)
    cmds = (0, 0, 0, cmd)
    done = None
    for _ in range(dm.AXI_TO_LIMIT + 64):
        out = model.cycle(valid, cmds, (0, 0, 0, 0), (0, 0, 0, 1), ip)
        if out.done:
            done = out
            break
    assert done is not None
    assert done.done == 1 << 3            # `done` fired ...
    assert done.read_cmpl is False        # ... but it was NOT a completed read
    assert done.to_abort is True
    assert done.to_err == 1
    assert done.cmd_to_err[3] == 1

    # contrast: a genuine completion clears the abort/error indicators
    model2 = dm.Ddr3CtrlAxiModel()
    ip2 = dm.ReadyIp(aw_latency=0, w_latency=0, ar_latency=0)
    done2 = None
    for _ in range(64):
        out = model2.cycle(valid, cmds, (0, 0, 0, 0), (0, 0, 0, 1), ip2)
        if out.done:
            done2 = out
            break
    assert done2 is not None
    assert done2.read_cmpl is True
    assert done2.to_abort is False and done2.to_err == 0
