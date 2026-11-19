"""Playback must preserve the user's selected volume and mute state."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows waveOut API')


def test_streaming_player_does_not_set_endpoint_volume(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    import audio_player as ap

    volume_calls = []

    def set_volume(*args):
        volume_calls.append(args)
        return 0

    fake = SimpleNamespace(
        waveOutOpen=lambda *args: 0,
        waveOutSetVolume=set_volume,
        waveOutPrepareHeader=lambda *args: 0,
        waveOutWrite=lambda *args: 0,
        waveOutReset=lambda *args: 0,
        waveOutUnprepareHeader=lambda *args: 0,
        waveOutClose=lambda *args: 0,
    )
    monkeypatch.setattr(ap.ctypes, 'WinDLL', lambda name: fake)
    monkeypatch.setattr(ap, 'resolve_device', lambda hint: 2 if hint == 'NICEHCK' else -1)
    monkeypatch.setattr(ap.threading, 'Thread', lambda **kw: SimpleNamespace(
        start=lambda: None, join=lambda **kw: None))
    pcm = np.arange(1024, dtype=np.int16)
    player = ap.StreamingPlayer(pcm, device_hint='NICEHCK', gain_db=0).start()
    try:
        assert player.device_id == 2
        assert np.array_equal(player.pcm.reshape(-1, 2)[:, 0], pcm)
        assert volume_calls == []
    finally:
        player.stop()
