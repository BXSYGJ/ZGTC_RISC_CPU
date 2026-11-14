#!/usr/bin/env python3
"""Score the board on the Medley-solos-DB 8-class demo clips (in-domain).

Why this tool exists
--------------------
The IRMAS excerpts are outside the model's training distribution (offline scores
~17%), so a board number there measures the model, not the FPGA.  These demo
clips are the model's OWN domain -- one clip per class, labelled by filename
(sample_N_<name>.wav) -- so the board should land near the model's reported 77%
if the whole chain is healthy.

Two measurement traps this tool guards against (both produced bogus 1/8 runs):

* **Muted / dead output.**  A muted endpoint or a loose 3.5 mm plug still
  accepts waveOut without error, so the board records silence and every clip
  collapses to the same logits.  Guard: unmute + pin the endpoint volume, then
  require the board's own PCM std to clear ``--std-min`` before trusting a
  capture (replay otherwise).
* **Stale / discontinuous window.**  The diag lock freezes whichever ping-pong
  half the Mel engine is about to consume; right after playback starts that
  half can still hold the tail of the previous capture (audio then silence),
  which makes the classifier see mostly silence and score nonsense.  Guard:
  read the half back and require every 8 KiB block to carry signal, else
  unlock, wait and re-capture.

The report separates three numbers, because they answer three different
questions:

    board            what the FPGA's NPU actually produced
    goldCap          golden run on the *same* window the FPGA consumed
                     -> must equal `board`; if it does, the FPGA chain is
                        correct and any accuracy gap is upstream
    clean            golden run on the clip as played, i.e. what the board
                     should have heard

Usage
-----
    python scripts/board_demo.py --device-hint NICEHCK
    python scripts/board_demo.py --demo-dir D:/0000/111/001/Pango/InstRec/data/demo --json out.json
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

import board_accuracy as ba                      # noqa: E402

DEFAULT_DEMO = Path("D:/0000/111/001/Pango/InstRec/data/demo")


def prep_clip_any(path: Path, peak_dbfs: float = -1.0) -> np.ndarray:
    """Like ba.prep_clip but also accepts float32 (WAVE_FORMAT_IEEE_FLOAT) wavs.

    The demo clips ship as 32-bit float, which Python's wave module rejects, so
    fall back to scipy.io.wavfile and normalise to int16 before resampling.
    """
    try:
        return ba.prep_clip(path, peak_dbfs)
    except Exception:
        from scipy.io import wavfile
        sr, x = wavfile.read(path)
        x = np.asarray(x, dtype=np.float64)
        m = max(abs(float(x.max())), abs(float(x.min())), 1e-9)
        x = np.clip(x / m, -1.0, 1.0) * 32767.0
        x = x.round().astype(np.int16)
        if x.ndim == 2:
            x = x[:, 0]
        x = ba.resample_to_48k(x, sr)
        peak = float(np.abs(x).max()) or 1.0
        target = 32767.0 * (10.0 ** (peak_dbfs / 20.0))
        return np.clip(x * (target / peak), -32768, 32767).round().astype(np.int16)


def prepare_endpoint(hint: str, volume: int) -> None:
    """Unmute the render endpoint and pin its volume.

    A muted endpoint still accepts waveOut without error, so the board simply
    records silence and every clip collapses to the same logits.
    """
    try:
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except Exception as exc:                                  # pragma: no cover
        print("  (pycaw unavailable, cannot check mute: %s)" % exc)
        return
    for d in AudioUtilities.GetAllDevices():
        name = str(d.FriendlyName)
        if hint.lower() not in name.lower() or name.startswith("麦克风"):
            continue
        try:
            vol = d._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                                  ).QueryInterface(IAudioEndpointVolume)
        except Exception:
            continue
        was_muted = bool(vol.GetMute())
        vol.SetMute(0, None)
        vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, volume / 100.0)), None)
        print("  endpoint '%s': mute %s -> 0, volume -> %d%%"
              % (name, was_muted, volume))
        return
    print("  (no endpoint matched %r; leaving audio settings alone)" % hint)


def window_continuity(pcm: np.ndarray, block: int = 8192, floor: float = 200.0) -> float:
    """Fraction of blocks that carry signal.  A gap (stale half) shows up here."""
    if pcm.size < block:
        return 0.0
    env = np.array([np.abs(pcm[i:i + block]).max()
                    for i in range(0, pcm.size - block + 1, block)])
    return float((env > floor).mean())


def golden_logits(pcm, tables, contract, weights, rec):
    import golden_pipeline as gp
    feat = gp.run_mel_pipeline(pcm, tables,
                               inv_s_in=int(rec["inv_s_in"]),
                               zp_in=int(rec["zp_in"]))["feat"]
    out = gp.npu_forward(feat, contract, tables["exp_lut"], weights=weights)
    return int(out["top1"]), [int(v) for v in out["logits"]]


def capture_window(ser, dd, ds, half_rule: str, window: int):
    """Lock, read the half the Mel engine consumes, return (win, half, pcm)."""
    dd.read_status(ser)
    ser.write(b"L")
    time.sleep(0.05)
    st = dd.read_status(ser)
    win = st["win"]
    half = (0 if (win & 1) else 1) if half_rule == "prev" else (win & 1)
    raw = ds.read_ddr_robust(ser, dd.PCM_LASE + dd.PCM_WIN_STRIDE * half,
                             dd.PCM_WIN_BYTES)
    ser.write(b"U")
    time.sleep(0.05)
    pcm = np.frombuffer(raw, dtype="<i2").astype(np.int16)[:window]
    return win, half, pcm


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-dir", default=str(DEFAULT_DEMO))
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--wait", type=float, default=10.0,
                    help="seconds of playback before locking")
    ap.add_argument("--json", default=None)
    ap.add_argument("--device-hint", default="NICEHCK",
                    help="render endpoint to play into (default NICEHCK: the 3.5 mm "
                         "cable currently hangs off that DAC)")
    ap.add_argument("--no-unmute", action="store_true",
                    help="do not touch the endpoint mute/volume")
    ap.add_argument("--volume", type=int, default=50)
    ap.add_argument("--attempts", type=int, default=4, help="captures per clip")
    ap.add_argument("--std-min", type=float, default=300.0,
                    help="minimum board PCM std for a capture to count")
    ap.add_argument("--min-fill", type=float, default=0.3,
                    help="minimum fraction of 8 KiB blocks that must carry signal. "
                         "Music clips legitimately contain rests, so this is only a "
                         "sanity floor -- a dead link reads ~0.0")
    ap.add_argument("--half", choices=("prev", "curr"), default="prev",
                    help="ping-pong half the Mel engine consumes; 'prev' matches the "
                         "win_base fix (bitstream 20261113 onward)")
    args = ap.parse_args(argv)

    import audio_player as apx
    import diag_dump as dd
    import diag_spectrum as ds
    import golden_pipeline as gp
    import serial

    demo = Path(args.demo_dir)
    clips = sorted(demo.glob("sample_*.wav"))
    if not clips:
        print("no sample_*.wav under %s" % demo, file=sys.stderr)
        return 2

    tables = gp.load_mel_tables(SCRIPTS / "outputs" / "mel_tables_48k.json")
    contract = gp.load_layer_contract(SCRIPTS / "outputs" / "medley_48k" / "layer_contract.json")
    weights = gp.load_weights_from_image(contract, SCRIPTS / "outputs" / "medley_48k" / "weights_image.bin")
    rec = contract.get("quant_stub_input_contract", contract)
    window = gp.WINDOW_SAMPLES

    ser = serial.Serial(args.port, 115200, timeout=0.4)
    time.sleep(0.2)
    dev = apx.resolve_device(args.device_hint)
    print("play device = %s (%d)" % (args.device_hint, dev))
    if not args.no_unmute:
        prepare_endpoint(args.device_hint, args.volume)

    rows = []
    ok = same = clean_ok = 0
    for clip in clips:
        truth = int(clip.stem.split("_")[1])
        pcm48 = prep_clip_any(clip, -1.0)
        unit = np.tile(pcm48, int(np.ceil(window / max(1, pcm48.size))))[:window]
        # Long enough to survive every capture attempt: reading one ping-pong
        # half back takes ~31 s over 115200 baud, so a short buffer runs dry
        # mid-retry and the captured window ends up half silence.
        pcm = ba.loop_to(unit, args.wait + 60 * max(1, args.attempts))

        # One continuous playback, several capture attempts.  Restarting the
        # player for every retry was the original mistake: waveOut + the DAC
        # need ~2.5 s to actually start, so every retry landed on the same
        # silence-to-audio transition window (~50-70% fill) and never improved.
        cap = None
        std = fill = 0.0
        logits = []
        player = apx.StreamingPlayer(pcm, sr=48000, channels=2,
                                     device_hint=args.device_hint, gain_db=0.0,
                                     buf_ms=60, queued=4).start()
        try:
            time.sleep(args.wait)
            for attempt in range(1, max(1, args.attempts) + 1):
                std = ba.board_pcm_std(ser, dd)
                if std < args.std_min:
                    print("      attempt %d/%d: board PCM std %.0f < %.0f, waiting"
                          % (attempt, args.attempts, std, args.std_min))
                    time.sleep(1.5)
                    continue
                win, half, cand = capture_window(ser, dd, ds, args.half, window)
                fill = window_continuity(cand)
                if fill < args.min_fill:
                    print("      attempt %d/%d: win=%d half=%d only %.0f%% of the "
                          "window carries signal, waiting for a full window"
                          % (attempt, args.attempts, win, half, 100.0 * fill))
                    time.sleep(1.5)
                    continue
                logits = dd.read_logits(ser)
                cap = cand
                break
        finally:
            player.stop()
            time.sleep(0.3)

        if cap is None:
            rows.append({"file": str(clip), "truth": truth, "board": -1,
                         "golden_captured": -1, "golden_clean": -1,
                         "pcm_std": round(std, 1), "fill": round(fill, 3),
                         "logits": []})
            print("[%d/%d] %-36s truth=%d  NO VALID CAPTURE (std=%.0f fill=%.2f)"
                  % (len(rows), len(clips), clip.name, truth, std, fill))
            continue

        got = int(np.argmax(logits)) if logits else -1
        ref_cap, lg_cap = golden_logits(cap, tables, contract, weights, rec)
        ref_clean, _ = golden_logits(unit, tables, contract, weights, rec)

        hit = got == truth
        ok += hit
        same += (ref_cap == got)
        clean_ok += (ref_clean == truth)

        rows.append({"file": str(clip), "truth": truth, "board": got,
                     "golden_captured": ref_cap, "golden_clean": ref_clean,
                     "pcm_std": round(std, 1), "fill": round(fill, 3),
                     "logits": [int(v) for v in logits],
                     "logits_golden_captured": lg_cap})
        print("[%d/%d] %-36s truth=%d(%s) board=%d(%s) %s  goldCap=%d %s  clean=%d %s"
              "  std=%.0f fill=%.2f" % (
                  len(rows), len(clips), clip.name, truth, ba.CLASS_NAMES[truth][:9],
                  got, ba.CLASS_NAMES[got][:9] if got >= 0 else "?",
                  "OK  " if hit else "MISS", ref_cap,
                  "SAME" if ref_cap == got else "DIFF", ref_clean,
                  "OK" if ref_clean == truth else "MISS", std, fill))
        time.sleep(0.3)

    ser.close()
    n = len(rows)
    valid = sum(1 for r in rows if r["board"] >= 0)
    print("")
    print("BOARD accuracy            = %d/%d = %.1f%%   (valid captures %d/%d)"
          % (ok, n, 100.0 * ok / n, valid, n))
    print("board == golden(captured) = %d/%d" % (same, valid))
    print("golden(clean) accuracy    = %d/%d = %.1f%%" % (clean_ok, n, 100.0 * clean_ok / n))
    if args.json:
        import json
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("json:", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
