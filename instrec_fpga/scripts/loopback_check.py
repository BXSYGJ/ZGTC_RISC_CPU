#!/usr/bin/env python3
"""Verify the PC's playback with a digital (WASAPI/MME) loopback.

Plays a tone to a render endpoint and records the SAME audio back through a
loopback capture endpoint (Realtek "立体声混音" / Stereo Mix, or a virtual sound
card's microphone).  Because the capture is digital, any frequency change here
is a playback-stack defect; if the loopback shows the tone unchanged, the PC
playback path is exonerated and a downstream analogue loop must be the culprit.

Notes
-----
*  Stereo Mix is usually muted together with its parent speaker.  The tool
   unmutes the render endpoint for the duration of the measurement and restores
   the previous mute state afterwards.
*  Devices are resolved by NAME (indices drift with plug/unplug and driver
   state); pass --play-name / --cap-name to override.

Usage
-----
    python scripts/loopback_check.py                      # 1 kHz, Realtek + Stereo Mix
    python scripts/loopback_check.py --freq 3000 --seconds 2
    python scripts/loopback_check.py --list
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _pick(devices, name: str, want_out: bool):
    for idx, d in devices:
        if name.lower() in d["name"].lower():
            ok = d["max_output_channels"] if want_out else d["max_input_channels"]
            if ok:
                return idx
    return None


def _devices(hostapi_name: str):
    import sounddevice as sd

    apis = sd.query_hostapis()
    api_idx = next((i for i, a in enumerate(apis) if hostapi_name.lower() in a["name"].lower()), None)
    if api_idx is None:
        return []
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["hostapi"] == api_idx:
            out.append((i, d))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--amplitude", type=float, default=0.4)
    ap.add_argument("--play-name", default="Realtek")
    ap.add_argument("--cap-name", default="立体声混音")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    try:
        import sounddevice as sd
    except Exception as exc:
        print("sounddevice missing: %s" % exc, file=sys.stderr)
        return 2

    if args.list:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] or d["max_output_channels"]:
                print("%3d [%s] in=%d out=%d  %s" % (
                    i, sd.query_hostapis()[d["hostapi"]]["name"],
                    d["max_input_channels"], d["max_output_channels"], d["name"]))
        return 0

    # Same host API for both ends keeps a single sample rate valid.
    devices = _devices("WASAPI")
    play = _pick(devices, args.play_name, True)
    cap = _pick(devices, args.cap_name, False)
    if play is None or cap is None:
        devices = _devices("WDM-KS")
        play = _pick(devices, args.play_name, True) if play is None else play
        cap = _pick(devices, args.cap_name, False) if cap is None else cap
    if play is None or cap is None:
        print("could not resolve play/capture endpoint; use --list", file=sys.stderr)
        return 2

    info = sd.query_devices(cap)
    sr = int(info["default_samplerate"]) or 48000
    print("play device  = %d %s" % (play, sd.query_devices(play)["name"]))
    print("capture dev  = %d %s" % (cap, sd.query_devices(cap)["name"]))
    print("sample rate  = %d Hz, tone = %.1f Hz" % (sr, args.freq))

    # Unmute the render endpoint for the measurement (Stereo Mix follows it).
    restore = None
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL

        for d in AudioUtilities.GetAllDevices():
            if args.play_name.lower() in str(d.FriendlyName).lower():
                iface = d._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                v = iface.QueryInterface(IAudioEndpointVolume)
                restore = (v, v.GetMute())
                if restore[1]:
                    v.SetMute(0, None)
                    print("unmuted '%s' for the measurement" % d.FriendlyName)
                break
    except Exception as exc:
        print("volume guard unavailable: %s" % exc)

    try:
        n = int(sr * args.seconds)
        t = np.arange(n) / sr
        mono = (args.amplitude * np.sin(2 * np.pi * args.freq * t)).astype(np.float32)
        out = np.repeat(mono[:, None], 2, axis=1)
        buf = []

        def cb(indata, frames, ti, status):
            buf.append(indata.copy())

        with sd.InputStream(device=cap, samplerate=sr, channels=2,
                            dtype="float32", callback=cb):
            sd.play(out, samplerate=sr, device=play, blocking=False)
            sd.wait()
            time.sleep(0.3)
    finally:
        if restore is not None and restore[1]:
            restore[0].SetMute(1, None)
            print("render endpoint mute restored")

    data = np.concatenate(buf) if buf else np.zeros((1, 2))
    x = data[:, 0].astype(np.float64)
    x -= x.mean()
    if x.std() < 1e-5:
        print("RESULT: loopback silent (check Stereo Mix / virtual-cable routing)")
        return 1
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1.0 / sr)
    peak = float(freqs[int(np.argmax(spec))])
    print("RESULT: loopback peak = %.1f Hz (played %.1f, ratio %.4f)"
          % (peak, args.freq, peak / args.freq))
    return 0 if abs(peak - args.freq) < 0.02 * args.freq else 1


if __name__ == "__main__":
    raise SystemExit(main())
