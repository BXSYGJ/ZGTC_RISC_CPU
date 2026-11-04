#!/usr/bin/env python3
"""Offline health check + golden-domain analysis of an I2S capture.

No serial port involved: the input is the capture.wav / pcm.raw written
by scripts/i2s_capture.py. The check has two halves.

1. PCM health (capture quality):
   - left/right channel separability (distribution stats + correlation),
   - non-zero dynamics (std / min / max per channel),
   - clipping rate (samples pinned at the s16 rails),
   - 48 kHz duration cross-check against the capture manifest,
   - raw test-pattern detection (an L=n incrementing ramp written by an
     FPGA-side pattern generator, if that bitstream was used).

2. Golden Mel feature (the NPU comparison-chain origin):
   The capture point sits BEFORE the production 48 kHz -> 44.1 kHz FIR
   (147 phases x 96 taps, PCM1808 front-end), so the golden path is
   48k PCM --(FIR golden oracle)--> 44.1k PCM --(golden_pipeline
   run_mel_pipeline with the 44.1 kHz tables)--> uint8 feature
   (64 x 258). The FIR oracle is scripts/check_pcm1808.py:reference
   with the coefficients of gen_pcm1808_filter.coefficients -- an
   independent integer model of the RTL filter.
   If the FIR model cannot be imported the tool records a
   "FIR golden model gap" and degrades to running the 48 kHz PCM
   directly through the 48 kHz tables (mel_tables_48k.json) as a
   REFERENCE-ONLY feature (wrong domain for the production NPU input).

   Feature semantics after the 2026-11-04 quantization fix: saturation
   rate ~ 0, mean ~ 49 (the quint8 zero point), std ~ 16. The resulting
   feature is the ORIGIN OF THE COMPARISON CHAIN: it will be compared
   against the board-side NPU inference (feat-level cross-check).

Output: reports/i2s_capture_check_<label>.json (UTF-8, no BOM).

Usage (from instrec_fpga/):
  python scripts/i2s_capture_check.py --input build/i2s_capture/<label>_<stamp>/capture.wav \
      --manifest build/i2s_capture/<label>_<stamp>/manifest.json
  python scripts/i2s_capture_check.py --input build/i2s_capture/<...>/pcm.raw
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import wave
from pathlib import Path

import numpy as np

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
REPORTS_DIR = ROOT / 'reports'
OUT_ROOT = ROOT / 'build' / 'i2s_capture'

SAMPLE_RATE = 48000
CHANNELS = 2
S16_MIN, S16_MAX = -32768, 32767
FIR_MODEL_REF = 'scripts/check_pcm1808.py:reference (coeff: gen_pcm1808_filter.coefficients)'
TABLES_44K = SCRIPTS_DIR / 'outputs' / 'mel_tables.json'
TABLES_48K = SCRIPTS_DIR / 'outputs' / 'mel_tables_48k.json'


def import_module_from(path, name):
    """Import a module by file path (experiments/diag_float_domain pattern)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# PCM loading and channel statistics.
# ---------------------------------------------------------------------------
def load_pcm(path):
    """Read a capture as (pcm_bytes, source_kind, wav_rate, wav_channels).

    .wav files are read through the wave module (rate/channels from the
    header); any other extension is treated as raw LE s16 stereo 48 kHz.
    """
    path = Path(path)
    if path.suffix.lower() == '.wav':
        with wave.open(str(path), 'rb') as wf:
            assert wf.getsampwidth() == 2, 'expected 16-bit samples'
            rate, channels = wf.getframerate(), wf.getnchannels()
            raw = wf.readframes(wf.getnframes())
        return raw, 'wav', rate, channels
    return path.read_bytes(), 'raw', SAMPLE_RATE, CHANNELS


def split_channels(pcm_bytes):
    """Split interleaved {R,L} s16 LE bytes into (left, right) int16 arrays.

    The frame payload order is {R,L} per sample pair; index 0 of each pair
    is therefore the RIGHT channel and index 1 the LEFT channel. Both are
    returned as (left, right) so callers stay domain-explicit.
    """
    samples = np.frombuffer(bytes(pcm_bytes), dtype='<i2').astype(np.int16)
    if samples.size % 2:
        samples = samples[:-1]
    right = samples[0::2]
    left = samples[1::2]
    return left, right


def clip_rate(x):
    """Fraction of samples pinned at the s16 rails (hard clipping)."""
    return float(np.mean((x == S16_MAX) | (x == S16_MIN)))


def channel_stats(x):
    return {
        'mean': float(np.mean(x)),
        'std': float(np.std(x)),
        'min': int(np.min(x)),
        'max': int(np.max(x)),
        'nonzero_rate': float(np.mean(x != 0)),
        'clip_rate': clip_rate(x),
    }


def channel_correlation(left, right):
    """Pearson correlation of L/R, or None when a channel is constant."""
    if np.std(left) == 0 or np.std(right) == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def channels_separable(left, right):
    """True when L and R are not sample-identical wires.

    Judged by the correlation being below ~1 OR a visible difference in
    the channel mean/std (>= 1 LSB of drift between the distributions).
    """
    corr = channel_correlation(left, right)
    if corr is None:
        return False
    if abs(corr) < 0.999:
        return True
    return (abs(float(np.mean(left)) - float(np.mean(right))) >= 1.0
            or abs(float(np.std(left)) - float(np.std(right))) >= 1.0)


def detect_ramp_pattern(x, min_run=64):
    """Detect an L=n incrementing test pattern (the FPGA pattern generator).

    Looks for the longest run of consecutive samples differing by exactly
    +1, in the signed domain or across the u16 wrap (32767 -> -32768).
    Returns {'detected': bool, 'run_length': int, 'wrap_aware': bool}.
    """
    if x.size < 2:
        return {'detected': False, 'run_length': 0, 'wrap_aware': False}
    u16 = x.astype(np.uint16)
    delta = (np.diff(u16).astype(np.uint16) == 1)
    best = 0
    run = 0
    for d in delta:
        run = run + 1 if d else 0
        best = max(best, run)
    best += 1  # run of `run` steps spans run+1 samples
    return {'detected': bool(best >= min_run),
            'run_length': int(best),
            'wrap_aware': True}


# ---------------------------------------------------------------------------
# FIR golden model (48 kHz -> 44.1 kHz, 147 phases x 96 taps).
# ---------------------------------------------------------------------------
def load_fir_model():
    """Import the check_pcm1808 FIR oracle; None when unavailable."""
    try:
        if str(SCRIPTS_DIR) not in sys.path:
            sys.path.insert(0, str(SCRIPTS_DIR))
        import check_pcm1808
        import gen_pcm1808_filter
    except ImportError:
        return None
    return check_pcm1808, gen_pcm1808_filter


def fir_48k_to_44k1(stereo_s16):
    """Run the integer FIR oracle on (N, 2) s16 stereo input.

    Returns (out_int16 (M, 2), model_ref) or (None, None) when the golden
    FIR model is not importable (the caller degrades to the 48 kHz path).
    """
    mods = load_fir_model()
    if mods is None:
        return None, None
    check_pcm1808, gen_pcm1808_filter = mods
    coeff = gen_pcm1808_filter.coefficients()
    pairs = np.asarray(stereo_s16, dtype=np.int64)
    out = check_pcm1808.reference(pairs, coeff)
    return out.astype(np.int16), FIR_MODEL_REF


def downmix_mono(stereo):
    """Integer round-half-up stereo downmix (golden load_pcm_s16 parity)."""
    left = stereo[:, 1].astype(np.int32)
    right = stereo[:, 0].astype(np.int32)
    return ((left + right + 1) >> 1).astype(np.int16)


# ---------------------------------------------------------------------------
# Golden Mel feature.
# ---------------------------------------------------------------------------
def mel_feature_stats(pcm_mono, window_samples=132096, tables_path=None):
    """Run golden_pipeline.run_mel_pipeline and summarise the uint8 feat.

    pcm_mono is a 1-D int16 array at the TABLE sampling rate (44.1 kHz on
    the FIR path, 48 kHz on the degraded path); it is zero-padded / cut to
    the 3 s hardware window exactly like load_pcm_s16.
    """
    golden = import_module_from(SCRIPTS_DIR / 'golden_pipeline.py',
                                'golden_pipeline_i2s_check')
    tables = golden.load_mel_tables(Path(tables_path) if tables_path
                                    else golden.DEFAULT_TABLES_PATH)
    pcm = np.asarray(pcm_mono, dtype=np.int16)
    if pcm.size < window_samples:
        pcm = np.pad(pcm, (0, window_samples - pcm.size))
    pcm = pcm[:window_samples].copy()
    stages = golden.run_mel_pipeline(pcm, tables)
    feat = stages['feat']
    return {
        'tables': str(tables_path if tables_path else golden.DEFAULT_TABLES_PATH),
        'table_rate': int(tables['params']['sr']),
        'feat_shape': list(feat.shape),
        'feat_sat_rate': float(np.mean((feat == 255) | (feat == 0))),
        'feat_mean': float(np.mean(feat)),
        'feat_std': float(np.std(feat)),
    }, feat


def analyse(args):
    """Full offline analysis; returns the report dict."""
    pcm_bytes, source, rate, channels = load_pcm(args.input)
    left, right = split_channels(pcm_bytes)
    report = {
        'input': str(Path(args.input)),
        'label': args.label,
        'pcm': {
            'source': source,
            'bytes': len(pcm_bytes),
            'sample_rate': rate,
            'channels': channels,
            'stereo_frames': int(left.size),
            'duration_s': left.size / rate if rate else None,
        },
    }

    manifest = None
    if args.manifest:
        with open(args.manifest, 'r', encoding='utf-8') as fh:
            manifest = json.load(fh)
        report['manifest'] = {
            'frame_cnt': manifest.get('frame_cnt'),
            'crc_errors': manifest.get('crc_errors'),
            'seconds': manifest.get('seconds'),
        }
        expected = manifest.get('frame_cnt')
        if expected is not None:
            report['pcm']['duration_match'] = bool(
                expected * 256 == len(pcm_bytes))
            report['pcm']['duration_expected_s'] = manifest.get('seconds')
    corr = channel_correlation(left, right)
    report['channels'] = {
        'left': channel_stats(left),
        'right': channel_stats(right),
        'correlation': corr,
        'separable': channels_separable(left, right),
    }
    report['pattern'] = detect_ramp_pattern(left)
    if not report['pattern']['detected']:
        right_pattern = detect_ramp_pattern(right)
        if right_pattern['detected']:
            report['pattern'] = dict(right_pattern, channel='right')
        else:
            report['pattern'] = dict(report['pattern'], channel='left')

    # Golden domain: FIR first, 48 kHz tables only as the degraded path.
    stereo = np.stack([right, left], axis=1).astype(np.int16)
    if not args.no_golden:
        golden_report = {}
        out44, model_ref = fir_48k_to_44k1(stereo)
        if out44 is not None:
            print(f'FIR golden model: {model_ref} '
                  f'({stereo.shape[0]} -> {out44.shape[0]} frames); '
                  f'running mel pipeline (44.1 kHz tables)')
            mono = downmix_mono(out44)
            stats, _ = mel_feature_stats(mono, tables_path=TABLES_44K)
            golden_report['mode'] = 'fir_44k'
            golden_report['fir_model'] = model_ref
            golden_report['fir_input_frames'] = int(stereo.shape[0])
            golden_report['fir_output_frames'] = int(out44.shape[0])
        else:
            print('FIR golden model gap: check_pcm1808 not importable; '
                  'degrading to the 48 kHz tables (reference-only feature)')
            mono = downmix_mono(stereo)
            stats, _ = mel_feature_stats(mono, tables_path=TABLES_48K)
            golden_report['mode'] = 'fallback_48k_reference_only'
            golden_report['fir_model'] = None
            golden_report['fir_model_gap'] = (
                'FIR golden model gap: 48k->44.1k oracle unavailable, '
                'feature computed with mel_tables_48k.json is NOT the '
                'production NPU input domain')
        golden_report.update(stats)
        golden_report['reference_semantics'] = (
            'post-fix semantics: feat saturation ~ 0, mean ~ 49 (zp_in), '
            'std ~ 16')
        golden_report['usage'] = (
            'this feature is the origin of the comparison chain: it will '
            'be cross-checked against the board-side NPU inference')
        report['golden'] = golden_report

    health = {
        'nonzero_dynamics': bool(np.std(left) > 0 or np.std(right) > 0),
        'channels_separable': report['channels']['separable'],
        'clip_free': bool(report['channels']['left']['clip_rate'] < 0.01
                          and report['channels']['right']['clip_rate'] < 0.01),
        'pattern_detected': report['pattern']['detected'],
    }
    report['health'] = health
    report['verdict'] = 'PASS' if (health['nonzero_dynamics']
                                   and health['clip_free']) else 'FAIL'
    report['conclusion'] = (
        'PC-side capture quality check; the golden feature recorded here '
        'is the true-chain origin and will be compared against the '
        'board-side NPU inference')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--input', required=True,
                    help='capture.wav or pcm.raw written by i2s_capture.py')
    ap.add_argument('--manifest', default=None,
                    help='optional manifest.json next to the capture '
                         '(duration / frame_cnt cross-check)')
    ap.add_argument('--label', default=None,
                    help='report label (default: input file stem)')
    ap.add_argument('--no-golden', action='store_true',
                    help='skip the FIR + mel golden analysis')
    args = ap.parse_args(argv)
    if args.label is None:
        args.label = Path(args.input).stem

    report = analyse(args)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f'i2s_capture_check_{args.label}.json'
    with open(out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in
                      ('label', 'pcm', 'health', 'verdict')}, indent=2))
    print(f'report: {out}')
    return 0 if report['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
