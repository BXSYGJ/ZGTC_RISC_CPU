"""Unit tests for the I2S capture PC tools (i2s_capture / i2s_capture_check).

Pure offline logic only -- no serial port, no board, no playback:
  1. CRC-16/CCITT-FALSE matches the standard check vector AND the
     weight_upload implementation byte for byte (cross-check of the two
     independently kept copies of the same protocol CRC).
  2. Data-frame codec roundtrip (build_frame -> parse_frame) plus the
     corruption paths (bad CRC, bad SOF, wrong length).
  3. Capture geometry (expected_frames / reassemble).
  4. pcm.raw bytes -> WAV write -> read back identity.
  5. manifest.json write -> read identity.
  6. i2s_capture_check helpers: {R,L} deinterleave, ramp pattern
     detection, channel separability, FIR golden model smoke test and
     the golden mel feature on an all-silent window (all-49 semantics).
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

import i2s_capture as ic
import i2s_capture_check as icc
import weight_upload as wu

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# CRC-16 / frame codec.
# ---------------------------------------------------------------------------
def test_crc16_ccitt_false_check_vector():
    # Standard CRC-16/CCITT-FALSE check value ("123456789" -> 0x29B1).
    assert ic.crc16_ccitt_false(b'123456789') == 0x29B1


def test_crc16_matches_weight_upload_implementation():
    rng = np.random.default_rng(20261104)
    for size in (0, 1, 17, 256, 1024):
        payload = rng.integers(0, 256, size, dtype=np.uint8).tobytes()
        assert ic.crc16_ccitt_false(payload) == wu.crc16_ccitt_false(payload)


def test_frame_roundtrip():
    rng = np.random.default_rng(7)
    payload = rng.integers(0, 256, 256, dtype=np.uint8).tobytes()
    frame = ic.build_frame(733, payload)
    seq, out = ic.parse_frame(frame)
    assert seq == 733
    assert out == payload


def test_frame_matches_weight_upload_layout():
    # Same wire format as the upload direction: byte-identical frames for
    # identical (seq, payload), CRC included.
    payload = bytes(range(64))
    assert ic.build_frame(3, payload) == wu.build_frame(3, payload)


def test_parse_frame_rejects_defects():
    payload = bytes(range(32))
    frame = bytearray(ic.build_frame(11, payload))
    frame[-1] ^= 0x01                       # CRC corruption
    with pytest.raises(ValueError):
        ic.parse_frame(bytes(frame))
    frame = bytearray(ic.build_frame(11, payload))
    frame[0] = 0xAB                         # SOF corruption
    with pytest.raises(ValueError):
        ic.parse_frame(bytes(frame))
    with pytest.raises(ValueError):         # truncated frame
        ic.parse_frame(ic.build_frame(11, payload)[:-4])
    with pytest.raises(ValueError):         # bad seq range
        ic.build_frame(0xFFFF, payload)


# ---------------------------------------------------------------------------
# Capture geometry.
# ---------------------------------------------------------------------------
def test_expected_frames():
    assert ic.expected_frames(4.0) == 3000          # 4 s * 750 frames/s
    assert ic.expected_frames(1.0) == 750
    # The FPGA read-back window quoted in the capture contract: 768
    # frames x 256 B = 196608 bytes of {R,L} interleaved s16 samples.
    assert 768 * ic.MAX_PAYLOAD == 196608


def test_reassemble():
    payloads = [bytes([seq]) * 4 for seq in range(5)]
    assert ic.reassemble(payloads) == b''.join(payloads)
    assert ic.reassemble([]) == b''


# ---------------------------------------------------------------------------
# Artifacts: WAV and manifest.
# ---------------------------------------------------------------------------
def test_pcm_bytes_wav_roundtrip(tmp_path):
    rng = np.random.default_rng(42)
    pcm = rng.integers(-32768, 32768, 2048, dtype=np.int16)
    pcm_bytes = pcm.astype('<i2').tobytes()
    wav_path = tmp_path / 'capture.wav'
    ic.write_wav(wav_path, pcm_bytes)
    with wave.open(str(wav_path), 'rb') as wf:
        assert wf.getframerate() == ic.SAMPLE_RATE
        assert wf.getnchannels() == 2
        assert wf.getsampwidth() == 2
        back = wf.readframes(wf.getnframes())
    assert back == pcm_bytes


def test_manifest_roundtrip(tmp_path):
    manifest = {
        'label': 'sine', 'frame_cnt': 768, 'crc_errors': 0,
        'uart_sha256': 'deadbeef' * 8, 't_c': '2026-11-04T10:00:00',
        't_d': '2026-11-04T10:00:04', 'verdict': 'PASS',
    }
    path = tmp_path / 'manifest.json'
    ic.write_manifest(path, manifest)
    text = path.read_text(encoding='utf-8')
    assert not text.startswith('\ufeff')           # UTF-8 without BOM
    assert ic.read_manifest(path) == manifest


def test_summary_keys_are_twelve():
    assert len(ic.SUMMARY_KEYS) == 12
    assert len(set(ic.SUMMARY_KEYS)) == 12


# ---------------------------------------------------------------------------
# i2s_capture_check helpers.
# ---------------------------------------------------------------------------
def test_split_channels_r_l_order():
    # Payload pairs are {R, L}: sample 0 of each pair is RIGHT, 1 is LEFT.
    pcm = np.array([10, 20, -30, -40], dtype='<i2').tobytes()
    left, right = icc.split_channels(pcm)
    assert list(left) == [20, -40]
    assert list(right) == [10, -30]


def test_detect_ramp_pattern():
    ramp = np.arange(512, dtype=np.int16)
    result = icc.detect_ramp_pattern(ramp)
    assert result['detected'] and result['run_length'] >= 512
    rng = np.random.default_rng(3)
    noise = rng.integers(-30000, 30000, 4096).astype(np.int16)
    assert not icc.detect_ramp_pattern(noise)['detected']
    # Wrap-aware: 32767 -> -32768 continues an incrementing ramp in u16.
    wrap = np.array([32760, 32761, 32762, 32763, 32764, 32765, 32766,
                     32767, -32768, -32767], dtype=np.int16)
    assert icc.detect_ramp_pattern(wrap, min_run=8)['detected']


def test_channels_separable():
    rng = np.random.default_rng(5)
    left = rng.integers(-5000, 5000, 4096).astype(np.int16)
    identical = left.copy()
    assert not icc.channels_separable(left, identical)
    assert icc.channels_separable(left, -identical)   # anti-phase wire
    shifted = (left.astype(np.int32) + 300).astype(np.int16)
    assert icc.channels_separable(left, shifted)
    silent = np.zeros(4096, dtype=np.int16)
    assert not icc.channels_separable(silent, silent)     # corr is None


def test_channel_stats_and_clip_rate():
    clipped = np.array([32767, -32768, 100, -100], dtype=np.int16)
    assert icc.clip_rate(clipped) == 0.5
    stats = icc.channel_stats(np.array([0, 1, 2, 3], dtype=np.int16))
    assert stats['min'] == 0 and stats['max'] == 3
    assert stats['clip_rate'] == 0.0


def test_fir_golden_model_smoke():
    mods = icc.load_fir_model()
    if mods is None:
        pytest.skip('FIR golden model (check_pcm1808) not importable')
    rng = np.random.default_rng(1808)
    stereo = rng.integers(-32768, 32768, (1600, 2)).astype(np.int16)
    out, model_ref = icc.fir_48k_to_44k1(stereo)
    assert out is not None and 'check_pcm1808' in model_ref
    # 147-phase resampler: 1600 input frames -> 1470 output frames.
    assert out.shape == ((1600 * 147) // 160, 2)
    assert out.dtype == np.int16
    assert int(out.min()) >= -32768 and int(out.max()) <= 32767


def test_downmix_mono_round_half_up():
    stereo = np.array([[6, 4], [5, 4], [-5, -4]], dtype=np.int16)
    # (L + R + 1) >> 1: (4+6+1)>>1=5, (4+5+1)>>1=5, (-4-5+1)>>1=-4.
    assert list(icc.downmix_mono(stereo)) == [5, 5, -4]


def test_mel_feature_stats_all_silent():
    # All-silent window -> all-49 feature (the quint8 zero point),
    # zero saturation: the post-fix semantics of the golden chain.
    stats, feat = icc.mel_feature_stats(np.zeros(132096, dtype=np.int16),
                                        tables_path=icc.TABLES_44K)
    assert stats['table_rate'] == 44100
    assert stats['feat_shape'] == [64, 258]
    assert stats['feat_sat_rate'] == 0.0
    assert stats['feat_mean'] == 49.0
    assert np.all(feat == 49)
