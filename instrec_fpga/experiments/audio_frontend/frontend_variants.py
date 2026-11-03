"""Float-domain front-end variants F0/F1/F2/F2b for InstRec-FPGA.

Study scope (dual-mode planning: 8-class instrument ID + 5-group activity):

  F0  production baseline : 48k -> 44.1k resample (soxr_hq, identical to
      librosa.load(sr=44100)), 2048 FFT / hop 512, 64 slaney Mel bins,
      fmax = 22050 Hz (scripts/outputs/mel_tables.json params).
  F1  native 48k          : resampler removed, 2048 FFT / hop 512,
      fmax = 24000 Hz (new Nyquist, Mel filterbank regenerated).
  F2  decimated 24k       : equiripple (Parks-McClellan/remez) FIR
      anti-alias filter + 2x decimation, 1024 FFT / hop 256 (same
      42.67 ms window / 10.67 ms hop as F1), fmax = 12000 Hz.
  F2b decimated 16k       : 3x decimation control route (pipeline only,
      accuracy recorded for reference), 1024 FFT / hop 256, fmax = 8000.

All variants share the production float-domain semantics of
InstRec/src/features.py (verified by the sanity check in run_compare.py):

    power spectrum |STFT|^2 -> slaney Mel filterbank -> power_to_db
    (ref=np.max, amin=1e-10, top_db=80) -> pad/truncate to N_FRAMES=258
    (right-pad if short, keep tail if long) -> per-sample standardization
    (zero mean / unit variance over the whole spectrogram, eps=1e-6).

The Hann window and the Mel filterbank of every variant are generated the
same way scripts/gen_mel_tables.py does for F0:

    hann : librosa.filters.get_window("hann", n_fft, fftbins=True)
    mel  : librosa.filters.mel(sr, n_fft, n_mels=64, fmin=0,
                               fmax=min(fmax, Nyquist), htk=False,
                               norm="slaney")

except that F1/F2/F2b tables are regenerated for their own Nyquist
(fmax never exceeds the variant Nyquist).

Decimation FIRs are designed with scipy.signal.remez at the 48 kHz input
rate, 191 taps (odd, linear phase; group delay compensated by
scipy.signal.resample_poly).  Measured (see run_compare.py report):

    F2  : passband 0-10500 Hz, transition 10500-11700 Hz,
          stopband 11700-24000 Hz, ~81 dB stopband attenuation.
    F2b : passband 0-7000 Hz, transition 7000-8300 Hz,
          stopband 8300-24000 Hz, ~87 dB stopband attenuation.

Determinism: no randomness anywhere; fixed tables and fixed FIR
coefficients; repeated runs are byte-identical.
"""

from __future__ import annotations

from typing import Optional

import librosa
import numpy as np
from scipy import signal

# ---------------------------------------------------------------------------
# Shared contract constants (InstRec/src/features.py parity).
# ---------------------------------------------------------------------------
INPUT_SR = 48000            # physical PCM1808 front-end rate (48 kHz I2S)
N_FRAMES = 258              # fixed output frame count (production contract)
N_MELS = 64                 # Mel channels (all variants keep 64)
POWER = 2.0                 # power spectrum exponent
DB_AMIN = 1e-10             # power_to_db amin
DB_TOP_DB = 80.0            # power_to_db top_db
NORM_EPS = 1e-6             # per-sample standardization epsilon
F0_RES_TYPE = "soxr_hq"     # librosa.load / librosa.resample default

# Equiripple decimation FIR design (48 kHz input domain, odd tap count).
FIR_TAPS = 191
FIR_DESIGN_BANDS = {
    # variant -> (passband_edge, stopband_edge) in Hz @ 48 kHz input rate
    "F2": (10500.0, 11700.0),
    "F2b": (7000.0, 8300.0),
}

# ---------------------------------------------------------------------------
# Variant configuration table.
# ---------------------------------------------------------------------------
# window_ms / hop_ms: physical window and hop duration of one STFT frame.
# frames_per_3s: frames produced by a 3 s input (center=True, 1 + n/hop).
# frame_action: what the 258-frame contract does with frames_per_3s.
FRONTEND_CONFIGS = {
    "F0": {
        "variant": "F0",
        "role": "production baseline (mel_tables.json / features.py)",
        "sr": 44100,
        "decimation": None,
        "n_fft": 2048,
        "hop": 512,
        "n_mels": N_MELS,
        "fmin": 0.0,
        "fmax": 22050.0,
        "window_ms": 2048 / 44100 * 1000.0,
        "hop_ms": 512 / 44100 * 1000.0,
        "frames_per_3s": 259,
        "frame_action": "keep_tail_258_of_259",
    },
    "F1": {
        "variant": "F1",
        "role": "native 48k, resampler removed",
        "sr": 48000,
        "decimation": None,
        "n_fft": 2048,
        "hop": 512,
        "n_mels": N_MELS,
        "fmin": 0.0,
        "fmax": 24000.0,
        "window_ms": 2048 / 48000 * 1000.0,
        "hop_ms": 512 / 48000 * 1000.0,
        "frames_per_3s": 282,
        "frame_action": "keep_tail_258_of_282",
    },
    "F2": {
        "variant": "F2",
        "role": "24k decimated, FIR anti-alias, 42.67 ms window",
        "sr": 24000,
        "decimation": 2,
        "n_fft": 1024,
        "hop": 256,
        "n_mels": N_MELS,
        "fmin": 0.0,
        "fmax": 12000.0,
        "window_ms": 1024 / 24000 * 1000.0,
        "hop_ms": 256 / 24000 * 1000.0,
        "frames_per_3s": 282,
        "frame_action": "keep_tail_258_of_282",
    },
    "F2b": {
        "variant": "F2b",
        "role": "16k decimated control route (reference only)",
        "sr": 16000,
        "decimation": 3,
        "n_fft": 1024,
        "hop": 256,
        "n_mels": N_MELS,
        "fmin": 0.0,
        "fmax": 8000.0,
        "window_ms": 1024 / 16000 * 1000.0,
        "hop_ms": 256 / 16000 * 1000.0,
        "frames_per_3s": 188,
        "frame_action": "right_pad_188_to_258",
    },
}

VARIANTS = ("F0", "F1", "F2", "F2b")


# ---------------------------------------------------------------------------
# Table generation (same recipes as scripts/gen_mel_tables.py).
# ---------------------------------------------------------------------------
def hann_table(n_fft: int) -> np.ndarray:
    """Periodic Hann window, identical source as gen_mel_tables.py."""
    return librosa.filters.get_window("hann", n_fft, fftbins=True)


def mel_filterbank(sr: int, n_fft: int, fmax: float) -> np.ndarray:
    """Slaney-normalized Mel filterbank, identical recipe as gen_mel_tables.py.

    fmax is clamped to the variant Nyquist so the table is always valid.
    """
    nyquist = sr / 2.0
    return librosa.filters.mel(
        sr=sr,
        n_fft=n_fft,
        n_mels=N_MELS,
        fmin=0.0,
        fmax=float(min(fmax, nyquist)),
        htk=False,
        norm="slaney",
    )


# ---------------------------------------------------------------------------
# Decimation FIR design and measurement.
# ---------------------------------------------------------------------------
def design_decimation_fir(variant: str) -> np.ndarray:
    """Equiripple linear-phase FIR for the variant's decimation stage.

    Designed at the 48 kHz input rate; applied via resample_poly which
    compensates the (taps-1)/2 group delay (zero-phase alignment).
    """
    if variant not in FIR_DESIGN_BANDS:
        raise ValueError(f"variant {variant} has no decimation stage")
    pb_edge, sb_edge = FIR_DESIGN_BANDS[variant]
    bands = [0.0, pb_edge, sb_edge, float(INPUT_SR) / 2.0]
    return signal.remez(FIR_TAPS, bands, [1, 0], fs=INPUT_SR)


def fir_response_stats(variant: str) -> dict:
    """Measured passband ripple / stopband attenuation of the FIR (dB)."""
    h = design_decimation_fir(variant)
    pb_edge, sb_edge = FIR_DESIGN_BANDS[variant]
    w, mag = signal.freqz(h, worN=16384, fs=INPUT_SR)
    mag = np.abs(mag)
    pb = mag[w <= pb_edge]
    sb = mag[w >= sb_edge]
    return {
        "variant": variant,
        "taps": int(len(h)),
        "design": "scipy.signal.remez (equiripple, linear phase)",
        "passband_hz": [0.0, pb_edge],
        "transition_hz": [pb_edge, sb_edge],
        "stopband_hz": [sb_edge, INPUT_SR / 2.0],
        "passband_ripple_db": float(20.0 * np.log10(pb.max() / pb.min())),
        "stopband_attenuation_db": float(20.0 * np.log10(sb.max())),
        "group_delay_samples_at_48k": (len(h) - 1) // 2,
        "compensation": "scipy.signal.resample_poly zero-phase alignment",
    }


# ---------------------------------------------------------------------------
# Rate conversion.
# ---------------------------------------------------------------------------
def resample_f0(pcm48: np.ndarray) -> np.ndarray:
    """F0 rate conversion: 48 kHz -> 44.1 kHz (production soxr_hq path)."""
    return librosa.resample(
        pcm48.astype(np.float32),
        orig_sr=INPUT_SR,
        target_sr=44100,
        res_type=F0_RES_TYPE,
    )


def decimate_pcm(pcm48: np.ndarray, variant: str) -> np.ndarray:
    """F2/F2b rate conversion: FIR anti-alias + integer decimation."""
    h = design_decimation_fir(variant)
    decim = FRONTEND_CONFIGS[variant]["decimation"]
    return signal.resample_poly(pcm48.astype(np.float64), 1, decim, window=h)


# ---------------------------------------------------------------------------
# Production-parity spectrogram chain.
# ---------------------------------------------------------------------------
def pad_or_truncate_frames(mel: np.ndarray, n_frames: int = N_FRAMES) -> np.ndarray:
    """features.py _pad_or_truncate_frames semantics: right-pad zeros if
    short, keep the TAIL frames if long."""
    cur = mel.shape[1]
    if cur == n_frames:
        return mel
    if cur < n_frames:
        return np.pad(
            mel, ((0, 0), (0, n_frames - cur)),
            mode="constant", constant_values=0.0,
        )
    return mel[:, cur - n_frames:]


def per_sample_normalize(mel_db: np.ndarray) -> np.ndarray:
    """features.py _per_sample_normalize: zero mean / unit variance over
    the whole spectrogram, epsilon 1e-6."""
    mu = mel_db.mean()
    sigma = mel_db.std()
    return ((mel_db - mu) / (sigma + NORM_EPS)).astype(np.float32)


def run_frontend(
    pcm48: np.ndarray,
    variant: str,
    y_native: Optional[np.ndarray] = None,
) -> dict:
    """Run one front-end variant on a 48 kHz float PCM input.

    Parameters
    ----------
    pcm48 : np.ndarray
        1-D float waveform at INPUT_SR = 48 kHz (the physical front-end
        domain; all variants consume the SAME input signal).
    variant : str
        "F0" | "F1" | "F2" | "F2b".
    y_native : np.ndarray, optional
        Sanity-check hook: bypass the rate conversion and feed a waveform
        already at the variant sample rate (used to verify F0 parity with
        InstRec/src/features.py on a native 44.1 kHz signal).

    Returns
    -------
    dict with keys
        y            : waveform at the variant rate (post rate conversion)
        mel_power    : (64, frames_raw) Mel power spectrogram
        mel_db       : (64, 258) dB spectrogram after frame alignment
        z            : (64, 258) float32 standardized feature
        frames_raw   : frame count produced by the STFT (before alignment)
        frame_action : how frames_raw became 258
    """
    cfg = FRONTEND_CONFIGS[variant]

    if y_native is not None:
        y = np.asarray(y_native, dtype=np.float32)
    elif variant == "F0":
        y = resample_f0(pcm48)
    elif variant == "F1":
        y = np.asarray(pcm48, dtype=np.float32)
    else:
        y = decimate_pcm(pcm48, variant).astype(np.float32)

    win = hann_table(cfg["n_fft"])
    mel_fb = mel_filterbank(cfg["sr"], cfg["n_fft"], cfg["fmax"])

    S = librosa.stft(
        y,
        n_fft=cfg["n_fft"],
        hop_length=cfg["hop"],
        win_length=cfg["n_fft"],
        window=win,
        center=True,
        pad_mode="reflect",
    )
    power = np.abs(S) ** POWER
    mel_power = mel_fb @ power

    mel_db_full = librosa.power_to_db(
        mel_power, ref=np.max, amin=DB_AMIN, top_db=DB_TOP_DB
    )

    frames_raw = int(mel_db_full.shape[1])
    mel_db = pad_or_truncate_frames(mel_db_full, N_FRAMES)
    z = per_sample_normalize(mel_db)

    if frames_raw == N_FRAMES:
        action = "exact_258"
    elif frames_raw > N_FRAMES:
        action = f"keep_tail_258_of_{frames_raw}"
    else:
        action = f"right_pad_{frames_raw}_to_258"

    return {
        "y": y,
        "mel_power": mel_power,
        "mel_db": mel_db.astype(np.float32),
        "z": z,
        "frames_raw": frames_raw,
        "frame_action": action,
    }


# ---------------------------------------------------------------------------
# Deployment-domain quantization (8-class NPU input contract).
# ---------------------------------------------------------------------------
def quantize_uint8(z: np.ndarray, s_in: float, zp_in: int) -> np.ndarray:
    """Quantize the float feature to the uint8 NPU input image.

    Mirrors the fbgemm QuantStub semantics (round-half-to-even, then
    saturate to [0, 255]); verified bit-exact against
    torch.quantize_per_tensor by the run_compare.py sanity check.
    """
    q = np.round(z.astype(np.float64) / float(s_in)) + float(zp_in)
    return np.clip(q, 0.0, 255.0).astype(np.uint8)
