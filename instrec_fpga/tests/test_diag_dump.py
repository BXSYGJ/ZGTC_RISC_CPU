"""Offline checks for the board readback host script (no hardware).

Validates the frame parser and the 'R' request sequencing against frames
produced by the same builder the capture tools use, so the export format is
proven before a PDS build / flash.
"""
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import diag_dump as dd          # noqa: E402
import i2s_capture as cap      # noqa: E402


class FakeSer:
    """Minimal serial stand-in: reads from a byte queue, records writes."""

    def __init__(self, rx=b''):
        self._rx = io.BytesIO(rx)
        self.written = bytearray()
        self.timeout = 0.5

    def read(self, n=1):
        return self._rx.read(n)

    def write(self, data):
        self.written.extend(data)
        return len(data)

    def reset_input_buffer(self):
        pass


def test_read_frame_parses_a_built_frame():
    payload = bytes(range(256))
    frame = cap.build_frame(3, payload)
    ser = FakeSer(frame)
    seq, ln, got = dd.read_frame(ser)
    assert seq == 3
    assert ln == 256
    assert got == payload


def test_read_frame_rejects_bad_crc():
    frame = bytearray(cap.build_frame(1, b'\x11' * 256))
    frame[-1] ^= 0xFF
    ser = FakeSer(bytes(frame))
    assert dd.read_frame(ser) is None


def test_read_ddr_emits_expected_requests_and_reassembles():
    # 2 chunks of 256 B each; the fake device answers every 'R' with one frame.
    n_frames = 2
    payloads = [bytes([0xA0 + i]) * 256 for i in range(n_frames)]
    rx = b''.join(cap.build_frame(i, p) for i, p in enumerate(payloads))
    ser = FakeSer(rx)
    out = dd.read_ddr(ser, 0x1000, 512)
    assert out == b''.join(payloads)
    # request bytes: 'R' + addr(4 LE) + len(2 LE)
    assert ser.written[0:1] == b'R'
    assert int.from_bytes(ser.written[1:5], 'little') == 0x1000
    assert int.from_bytes(ser.written[5:7], 'little') == 512
    # one 'K' per frame
    assert ser.written.count(ord('K')) == n_frames


def test_pcm_window_split_stays_within_the_16bit_len_limit():
    # The 'R' length field is 16 bits, so a 264,192-byte window must be split
    # into requests that are 256-byte multiples and never exceed MAX_CHUNK.
    total, off, reqs = dd.PCM_WIN_BYTES, 0, []
    while off < total:
        chunk = min(dd.MAX_CHUNK, total - off)
        chunk -= chunk % 256
        if chunk == 0:
            chunk = 256
        reqs.append(chunk)
        off += chunk
    assert dd.MAX_CHUNK <= 65535
    assert all(c % 256 == 0 and 0 < c <= dd.MAX_CHUNK for c in reqs)
    assert sum(reqs) == total
    assert len(reqs) == 5          # 264,192 / 65,280 = 4.05 -> 5 requests


def test_logits_decode_is_little_endian_signed():
    vals = [-251, -224, -121, 252, -320, -50, 7, 0]
    payload = b''.join(v.to_bytes(4, 'little', signed=True) for v in vals)
    ser = FakeSer(cap.build_frame(0, payload.ljust(256, b'\x00')))
    assert dd.read_logits(ser) == vals
