#!/usr/bin/env python3
"""Calibrate the Realtek -> PCM1808 analog loop with pure tones.

Plays a set of single-frequency tones, reads back the exact PCM window the
board captured, and measures, per tone: the recovered fundamental frequency
(a systematic shift => sample-rate conversion), its RMS level (=> EQ /
loudness), and the 2nd/3rd harmonic power (=> clipping / nonlinearity).

Only the UART (COM5) and the Realtek endpoint are used -- no JTAG.

Usage
-----
    python scripts/loop_cal.py --freqs 200,500,1000,2000,4000,6000,8000,10000
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import diag_dump as dd            # noqa: E402
import diag_spectrum as ds        # noqa: E402

SR = 48000
READ_SAMPLES = 32768              # ~0.68 s of mono PCM


def synth(freq: float, amp: float = 0.5, seconds: float = 3.0) -> np.ndarray:
    n = int(round(SR * seconds))
    periods = max(1, int(round(freq * seconds)))
    f = periods / seconds
    t = np.arange(n) / SR
    mono = np.round(32767.0 * amp * np.sin(2 * np.pi * f * t)).astype(np.int16)
    return np.repeat(mono, 2)


def power_at(x: np.ndarray, f0: float, k: int) -> float:
    """Power in a +/-20 Hz band around k*f0, normalised to the fundamental."""
    N = len(x)
    w = np.hanning(N)
    X = np.fft.rfft((x - x.mean()) * w)
    freqs = np.fft.rfftfreq(N, 1.0 / SR)
    mag = np.abs(X) ** 2
    fundamental = 0.0
    for kk in (1, 2, 3, 4, 5):
        band = mag[(np.abs(freqs - kk * f0) <= 20.0)]
        if kk == 1:
            fundamental = float(band.max())
    if fundamental <= 0:
        return float("-inf")
    band = mag[(np.abs(freqs - k * f0) <= 20.0)]
    return 10.0 * np.log10(float(band.max()) / fundamental)


def analyze(pcm: np.ndarray) -> dict:
    x = pcm.astype(np.float64)
    x = x - x.mean()
    N = len(x)
    X = np.fft.rfft(x * np.hanning(N))
    freqs = np.fft.rfftfreq(N, 1.0 / SR)
    mag = np.abs(X)
    peak = int(np.argmax(mag))
    f0 = float(freqs[peak])
    rms = float(np.sqrt((x ** 2).mean()))
    return {"f0": f0, "rms": rms,
            "h2": power_at(x, f0, 2), "h3": power_at(x, f0, 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freqs", default="200,500,1000,2000,4000,6000,8000,10000")
    ap.add_argument("--amp-dbfs", type=float, default=-6.0,
                    help="tone amplitude (avoids clipping so THD is measurable)")
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--settle", type=float, default=3.0)
    args = ap.parse_args(argv)

    import serial
    from audio_player import StreamingPlayer

    amp = 10.0 ** (args.amp_dbfs / 20.0)
    freqs = [float(f) for f in args.freqs.split(",")]
    ser = serial.Serial(args.port, 115200, timeout=2.0)
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.write(b"U")
    time.sleep(0.05)

    print("freq(Hz)  f_captured  err(Hz)  rms(LSB)  H2(dB)  H3(dB)")
    for f in freqs:
        pcm_play = synth(f, amp=amp)
        player = StreamingPlayer(pcm_play, sr=SR, device_hint="Realtek",
                                 gain_db=0.0).start()
        time.sleep(args.settle)
        dd.read_status(ser)
        ser.write(b"L")
        time.sleep(0.05)
        st = dd.read_status(ser)
        win = st["win"]
        base = dd.PCM_LASE + (dd.PCM_WIN_STRIDE if not (win & 1) else 0)
        raw = ds.read_ddr_robust(ser, base, READ_SAMPLES * 2)
        ser.write(b"U")
        player.stop()

        pcm = np.frombuffer(raw, dtype="<i2").astype(np.float64)[:READ_SAMPLES]
        r = analyze(pcm)
        print("%9.0f  %9.1f  %7.1f  %8.1f  %6.1f  %6.1f" % (
            f, r["f0"], r["f0"] - f, r["rms"], r["h2"], r["h3"]))
        time.sleep(0.3)

    ser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
