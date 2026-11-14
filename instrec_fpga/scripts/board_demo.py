#!/usr/bin/env python3
"""Score the board on the Medley-solos-DB 8-class demo clips (in-domain).

The IRMAS excerpts are outside the model's training distribution (offline
scores ~17%), so a board accuracy number there only reflects the model, not
the FPGA.  These demo clips are the model's OWN domain -- one clip per class,
labelled by their filename (sample_N_<name>.wav) -- so the board should score
close to the model's reported 77% if the whole FPGA chain is healthy.

Each clip is peak-normalised, looped to a whole hardware window, played on the
Realtek endpoint, and its logits are read over the diag 'G' command.  The same
window is also run through the offline golden pipeline for a per-clip
board-vs-golden check.

Usage
-----
    python scripts/board_demo.py                 # data/demo/sample_*.wav (8 clips)
    python scripts/board_demo.py --demo-dir D:/0000/111/001/Pango/InstRec/data/demo
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo-dir", default=str(DEFAULT_DEMO))
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--wait", type=float, default=7.0)
    ap.add_argument("--reads", type=int, default=2)
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    import audio_player as apx
    import diag_dump as dd
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
    window = gp.WINDOW_SAMPLES

    ser = serial.Serial(args.port, 115200, timeout=0.4)
    time.sleep(0.2)
    dev = apx.resolve_device("Realtek")
    print("play device = Realtek (%d)" % dev)

    rows = []
    ok = 0
    agree = 0
    for clip in clips:
        truth = int(clip.stem.split("_")[1])
        pcm48 = prep_clip_any(clip, -1.0)
        unit = np.tile(pcm48, int(np.ceil(window / max(1, pcm48.size))))[:window]
        pcm = ba.loop_to(unit, args.wait + 4)

        player = apx.StreamingPlayer(pcm, sr=48000, channels=2,
                                     device_hint="Realtek", gain_db=0.0,
                                     buf_ms=60, queued=4).start()
        reads = []
        try:
            time.sleep(args.wait)
            for k in range(max(1, args.reads)):
                reads.append(dd.read_logits(ser))
                if k + 1 < max(1, args.reads):
                    time.sleep(2.5)
        finally:
            player.stop()

        logits = reads[-1] if reads else []
        votes = [int(np.argmax(r)) for r in reads]
        got = Counter(votes).most_common(1)[0][0] if votes else -1
        ref = ba.offline_top1(unit, tables, contract, weights, window)[0]
        hit = got == truth
        ok += hit
        agree += (ref == got)

        rows.append({"file": str(clip), "truth": truth, "board": got,
                     "offline": ref, "logits": [int(v) for v in logits]})
        print("[%d/%d] %-40s truth=%d(%s) board=%d(%s) %s  off=%d  logits=%s" % (
            len(rows), len(clips), clip.name, truth, ba.CLASS_NAMES[truth][:10],
            got, ba.CLASS_NAMES[got][:10] if got >= 0 else "?",
            "OK  " if hit else "MISS", ref, [int(v) for v in logits]))
        time.sleep(0.5)

    ser.close()
    n = len(rows)
    print("")
    print("BOARD accuracy on Medley-solos-DB demo = %d/%d = %.1f%%" % (ok, n, 100.0 * ok / n))
    print("board vs offline agreement            = %d/%d = %.1f%%" % (agree, n, 100.0 * agree / n))
    if args.json:
        import json
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print("json:", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
