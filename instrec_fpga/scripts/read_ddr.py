"""Formal DDR3 read-back with the measured command-address layout conversion.

Supersedes the throwaway tools under build/ (probe_addr_unit.py,
read_pcm_destride.py, win_scan.py, ...).  Every conversion lives in the pure,
unit-tested functions here (or in ddr3_layout.py); the serial transport is a
thin plug-in ``reader(cmd_addr) -> 256-byte frame`` so the geometry is testable
with no board attached.

Contract (docs/DDR3_CONTRACT_20261111.md section 6):

    physical_byte = ADDR_UNIT * cmd_addr + 32 * beat

Two bitstream generations exist and MUST NOT be confused:

  * NEW bitstream (after the ddr3_ctrl_axi >>2 fix): byte semantics,
    ADDR_UNIT = 1.  This is the DEFAULT (PROD_ADDR_UNIT): a 256-byte ``R``
    frame returns 8 whole contiguous pages, no de-striding needed.
  * OLD bitstream (SHA-256 69041235...): ADDR_UNIT = 4, the IP treats the
    command address as a word index.  Reading it requires LEGACY_X4_ADDR_UNIT
    and the destride reconstruction.  Do NOT pass LEGACY_X4_ADDR_UNIT for the
    new bitstream: it re-introduces the 3/4 aliasing this fix removes.
"""

from __future__ import annotations

from ddr3_layout import (FEAT_SLOT_BYTES, FRAME_BYTES, LEGACY_X4_ADDR_UNIT,
                         PAGE_BYTES, PROD_ADDR_UNIT, destride, frame_plan,
                         pages_for)

# --- Production PCM window (audio_sink, mono lane) --------------------------
PCM_CHANNELS = 1
PCM_SAMPLE_DTYPE = '<i2'        # int16, little endian
PCM_SAMPLES = 132096            # 8256 pages x 16 samples
PCM_BYTES = PCM_SAMPLES * 2     # 264,192
PCM_LEFT_BASE = 0x000000
PCM_RIGHT_BASE = 0x084000
PCM_WIN_STRIDE = 0x042000       # 264 KB ping-pong stride

# --- Production feature / spectrum region (mel_engine ST_SPECEX) ------------
# 16,512 x 16-bit slots = 33,024 B = 1,032 pages of 32 B.  The low byte of
# each slot is the uint8 feature (zp_in=49); the high byte is 0x00.
FEAT_BASE = 0x00200000
FEAT_ELEMENTS = 16512
FEAT_BYTES = FEAT_ELEMENTS * FEAT_SLOT_BYTES


def pcm_win_base(win):
    """Byte command address of the PCM window ``win`` (ping-pong)."""
    return PCM_LEFT_BASE + (PCM_WIN_STRIDE if (win & 1) else 0)


def region_plan(addr, length, addr_unit=PROD_ADDR_UNIT):
    """Return the frame plan that reads ``length`` logical bytes at ``addr``."""
    return frame_plan(addr, pages_for(length), addr_unit)


def read_region(reader, addr, length, addr_unit=PROD_ADDR_UNIT):
    """Read ``length`` logical bytes via ``reader(cmd_addr) -> 256 B frame``."""
    plan = frame_plan(addr, pages_for(length), addr_unit)
    frames = []
    for cmd_addr, _spans in plan:
        frame = reader(cmd_addr)
        if len(frame) != FRAME_BYTES:
            raise ValueError('frame at 0x%06x is %d B, want %d'
                             % (cmd_addr, len(frame), FRAME_BYTES))
        frames.append(frame)
    return destride(frames, plan)


def read_pcm(reader, win, addr_unit=PROD_ADDR_UNIT):
    """Read the locked PCM window ``win`` as a de-strided int16 byte stream."""
    return read_region(reader, pcm_win_base(win), PCM_BYTES, addr_unit)


def read_feat(reader, addr_unit=PROD_ADDR_UNIT):
    """Read the 16,512 feature slots and return the uint8 element stream."""
    raw = read_region(reader, FEAT_BASE, FEAT_BYTES, addr_unit)
    return bytes(raw[0::FEAT_SLOT_BYTES])
