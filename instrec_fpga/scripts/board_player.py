#!/usr/bin/env python3
"""Dedicated board player: 2x pitch-up + peak normalisation, looped playback.

Why
---
The PCM1808 module on this board delivers half-frequency data (verified: PC
plays 1000 Hz, the board decodes 500 Hz, exactly 2:1, while the crystal, LRCK
and the FPGA receiver are all correct).  Rather than rebuild the bitstream, this
player compensates on the PC side:

  * **2x pitch-up** -- decimate the clip by 2 and play it at the native rate,
    i.e. play it twice as fast.  Every frequency doubles, so the PCM1808's
    half-frequency capture lands back on the correct pitch inside the board.
  * **peak normalisation** -- every clip is scaled to the same target peak, so
    the analogue level (and therefore the captured SNR) is identical across
    clips.  This is the "unify the volume" requirement.

Usage
-----
    python scripts/board_player.py --play clip.wav                # board mode
    python scripts/board_player.py --play clip.wav --no-double    # plain loop
    python scripts/board_player.py --play clip.wav --peak-dbfs -3 --seconds 10

Run `--probe` to verify the compensation on the board's PCM1808 diagnostic
bitstream (F field = zero crossings per second; a 1000 Hz clip must read
F ~= 2000 with --double, F ~= 1000 without).
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

SR = 48000


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    return x.mean(axis=1), int(sr)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    from scipy.signal import resample_poly
    from math import gcd

    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(x, int(sr_out) // g, int(sr_in) // g)


def pitch_up2(x: np.ndarray) -> np.ndarray:
    """Play twice as fast: decimate by 2 (anti-aliased), keep the native rate."""
    from scipy.signal import resample_poly

    return resample_poly(x, 1, 2)


def normalise(x: np.ndarray, peak_dbfs: float) -> np.ndarray:
    peak = float(np.abs(x).max()) or 1.0
    target = 10.0 ** (peak_dbfs / 20.0)
    return x * (target / peak)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--play", required=True, help="wav to play")
    ap.add_argument("--peak-dbfs", type=float, default=-6.0,
                    help="normalisation target (default -6 dBFS, same for every clip)")
    ap.add_argument("--no-double", action="store_true",
                    help="do NOT pitch up 2x (plain playback)")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after N seconds (0 = play until Ctrl+C)")
    ap.add_argument("--device-hint", default="NICEHCK")
    ap.add_argument("--gain-db", type=float, default=0.0,
                    help="extra digital gain on top of the normalisation")
    ap.add_argument("--probe", action="store_true",
                    help="read the board PCM1808 probe F field while playing")
    args = ap.parse_args(argv)

    from audio_player import StreamingPlayer

    path = Path(args.play)
    if not path.is_file():
        print("wav not found: %s" % path, file=sys.stderr)
        return 2

    x, sr = read_wav_mono(path)
    x = resample(x, sr, SR)
    x = normalise(x, args.peak_dbfs)
    if not args.no_double:
        x = pitch_up2(x)
    print("clip: %s  in=%d Hz  out=%d samples (%.2f s)  peak=%.1f dBFS  pitch=%s"
          % (path.name, sr, x.size, x.size / SR, args.peak_dbfs,
             "2x" if not args.no_double else "1x"))

    stereo = np.repeat(np.round(np.clip(x, -1, 1) * 32767.0).astype(np.int16)[:, None], 2, axis=1)
    stereo = stereo.reshape(-1)          # StreamingPlayer wants interleaved 1-D
    player = StreamingPlayer(stereo, sr=SR, channels=2, device_hint=args.device_hint,
                             gain_db=args.gain_db).start()

    ser = None
    if args.probe:
        import re
        import serial

        ser = serial.Serial("COM5", 115200, timeout=0.5)
        ser.reset_input_buffer()

    try:
        t0 = time.time()
        while True:
            time.sleep(0.2)
            if args.probe and ser is not None:
                data = ser.read(300)
                if data:
                    for ln in data.decode("ascii", "replace").splitlines():
                        m = re.search(r"E=([0-9A-F]{4})([0-9A-F]{4}).*F=([0-9A-F]{8})", ln)
                        if m:
                            mn = int(m.group(1), 16)
                            mx = int(m.group(2), 16)
                            mn -= 65536 if mn > 32767 else 0
                            mx -= 65536 if mx > 32767 else 0
                            print("  probe: F=%d -> %.1f Hz   amp=[%d,%d]"
                                  % (int(m.group(3), 16), int(m.group(3), 16) / 2.0, mn, mx))
                            break
            if args.seconds and (time.time() - t0) >= args.seconds:
                break
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()
        if ser is not None:
            ser.close()
    print("underruns:", player.underruns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
