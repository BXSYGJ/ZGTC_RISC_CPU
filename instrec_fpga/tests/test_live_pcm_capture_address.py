"""A valid PCM window is shorter than the DDR ping-pong slot containing it."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import diagnose_live_pcm as capture


@pytest.mark.parametrize('win,expected_half', [(41, 0), (42, 1)])
def test_completed_pcm_read_skips_slot_padding(monkeypatch, win, expected_half):
    # Model the physical DDR geometry independently of the capture helper.
    # A length-as-stride mistake would prepend 6144 bytes of padding on half 1.
    window_bytes = 264192
    slot_bytes = 270336
    first = b'A' * window_bytes
    second = b'B' * window_bytes
    ram = first + b'X' * (slot_bytes - window_bytes) + second
    calls = []

    def read(ser, address, length):
        calls.append((address, length))
        return ram[address:address + length]

    monkeypatch.setattr(capture.ds, 'read_ddr_robust', read)
    half, pcm = capture.read_completed_pcm(None, {'win': win})
    assert half == expected_half
    assert pcm == (first if half == 0 else second)
    assert calls == [(expected_half * slot_bytes, window_bytes)]
