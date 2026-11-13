#!/usr/bin/env python3
"""Compare the board's exported Mel dB spectrum against the golden pipeline.

Why this exists
---------------
The production bitstream exports the **dB spectrum** to DDR3 0x0020_0000 in
ST_SPECEX: 16,512 x int16 words (Q8.8 dB, frame-major, element = frame*64 +
mel).  It does NOT export the standardized uint8 feature -- that stays in the
on-chip bank and is consumed by the NPU directly (FEAT_DUMP_ON_M3 = 0).

Reading 0x0020_0000 as feat slots therefore returns the low bytes of a bunch of
negative dB values, i.e. uniform noise.  Every earlier "board feat vs golden
feat" comparison was invalid for exactly that reason.  This script compares the
right thing:

    board  0x0020_0000 as <i2  ->  reshape(258, 64).T  ->  (64, 258) Q8.8 dB
    golden run_mel_pipeline(pcm the board actually captured)["dbspec"]

Both sides consume the SAME PCM (pulled back under the diag lock, so the window
cannot be overwritten mid-read), so any difference is a real RTL defect in the
Mel chain: framer / Hann / FFT / power / COO / log2 / dB.

Because the dB spectrum is referenced to the per-window maximum
(dB = log2 - max_log2), it is amplitude invariant: the same clip played at
-20 dB must produce the same dB spectrum as at 0 dB.  --gain-db therefore
doubles as a direct test of "the board feature carries level instead of
timbre": if the two captures differ, the level leak is upstream of
standardization, inside the Mel chain itself.

Exit codes: 0 exact match, 1 mismatch, 2 usage/hardware.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import golden_pipeline as gp                      # noqa: E402
import diag_dump as dd                            # noqa: E402

TABLES_48K = SCRIPTS / "outputs" / "mel_tables_48k.json"

SR = 48000
PCM_SAMPLES = 132096
N_MELS = 64
N_FRAMES = 258
SPEC_WORDS = N_MELS * N_FRAMES          # 16,512 int16 dB words
SPEC_BYTES = SPEC_WORDS * 2             # 33,024
SPEC_BASE = 0x00200000


def synth_tone(freq: float, peak_dbfs: float = -1.0, seconds: float = 3.0) -> np.ndarray:
    """Seamless stereo loop: an integer number of periods, both channels equal."""
    n = int(round(SR * seconds))
    periods = max(1, int(round(freq * seconds)))
    f = periods / seconds
    t = np.arange(n) / SR
    amp = 32767.0 * (10.0 ** (peak_dbfs / 20.0))
    mono = np.round(amp * np.sin(2 * np.pi * f * t)).astype(np.int16)
    return np.repeat(mono, 2)


def _wire_args(addr: int, length: int) -> bytes:
    return addr.to_bytes(4, "little") + length.to_bytes(2, "little")


def _blocked_by_aa(addr: int, length: int) -> bool:
    """True when the command bytes hit the 0xAA black hole.

    instrec_top.v:793 routes a received byte to the diagnostic engine only when
    rx_byte_data != 8'hAA (the weight loader keeps the 0xAA55 frame header),
    so ANY 0xAA byte inside the 4-byte address or the 2-byte length is silently
    dropped by the diag FSM.  The remaining argument bytes then shift and the
    channel desynchronises, which is why 0xAA00-style addresses were
    unreadable.  Such blocks must come from a wider transfer that starts at a
    clean address.
    """
    return b"\xaa" in _wire_args(addr, length)


def _raw_read(ser, addr: int, length: int, tries: int = 6) -> bytes:
    for attempt in range(tries):
        if attempt:
            ser.write(b"K")
            time.sleep(0.20)
        try:
            ser.reset_input_buffer()
            ser.write(b"R")
            ser.write(_wire_args(addr, length))
            out = bytearray()
            good = True
            for _ in range(length // 256):
                fr = dd.read_frame(ser, timeout=1.0)
                if fr is None:
                    good = False
                    break
                out.extend(fr[2][:256])
                ser.write(b"K")
            if good and len(out) == length:
                return bytes(out)
        except Exception:
            pass
        time.sleep(0.12)
    raise RuntimeError("read failed at 0x%08x len %d" % (addr, length))


def read_block(ser, addr: int) -> bytes:
    """One 256 B block, detouring around the 0xAA command-byte black hole."""
    if not _blocked_by_aa(addr, 256):
        return _raw_read(ser, addr, 256)
    for back in (256, 512, 768):
        base = addr - back
        if base >= 0 and not _blocked_by_aa(base, back + 256):
            return _raw_read(ser, base, back + 256)[back:back + 256]
    raise RuntimeError("no clean address window for 0x%08x" % addr)


def read_ddr_robust(ser, addr: int, length: int, progress: bool = False) -> bytes:
    """Read DDR 256 B at a time; a block is only trusted after a clean CRC.

    The production top level also emits a periodic UART telemetry line on the
    same wire, which occasionally lands inside a frame and breaks the CRC.  One
    command per block keeps that a local retry, and the region is frozen under
    the diag lock anyway.
    """
    assert length % 256 == 0
    out = bytearray()
    for i in range(length // 256):
        out.extend(read_block(ser, addr + 256 * i))
        if progress and (i % 128 == 0):
            print("    ...0x%08x (%d/%d)" % (addr + 256 * i, i, length // 256),
                  flush=True)
    return bytes(out)


def load_wav_stereo(path: Path) -> np.ndarray:
    import wave

    with wave.open(str(path), "rb") as wf:
        assert wf.getsampwidth() == 2, "expects 16-bit wav"
        assert wf.getframerate() == SR, f"wav rate {wf.getframerate()} != {SR}"
        ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    s = np.frombuffer(raw, dtype="<i2")
    if ch == 1:
        s = np.repeat(s, 2)
    elif ch > 2:
        s = s.reshape(-1, ch)[:, :2].reshape(-1)
    return s.astype(np.int16)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM5")
    ap.add_argument("--label", required=True)
    ap.add_argument("--freq", type=float, default=200.0, help="synth tone frequency")
    ap.add_argument("--peak-dbfs", type=float, default=-1.0)
    ap.add_argument("--gain-db", type=float, default=0.0, help="digital playback gain")
    ap.add_argument("--play", default=None, help="48 kHz stereo wav (else synth tone)")
    ap.add_argument("--settle", type=float, default=4.0, help="seconds before locking")
    ap.add_argument("--half", choices=("prev", "curr", "both"), default="prev",
                    help="which PCM ping-pong half the Mel engine consumed: "
                         "'prev' = ~win_id[0] (bitstreams with the mel_engine "
                         "win_base fix, 2026-11-13 onward), 'curr' = win_id[0] "
                         "(the 20261112-202047 bitstream), 'both' = read and "
                         "score both")
    ap.add_argument("--repeat", type=int, default=1, help="independent captures")
    args = ap.parse_args(argv)

    import serial
    from audio_player import StreamingPlayer

    pcm_play = load_wav_stereo(Path(args.play)) if args.play else synth_tone(args.freq, args.peak_dbfs)

    tables = gp.load_mel_tables(TABLES_48K)
    print("tables: sr=%s n_mels=%s n_frames=%s" % (
        tables["params"].get("sr"), tables["params"].get("n_mels"),
        tables["params"].get("n_frames")))

    results = []
    for run in range(args.repeat):
        ser = serial.Serial(args.port, 115200, timeout=2.0)
        player = None
        try:
            time.sleep(0.2)
            ser.reset_input_buffer()
            ser.write(b"U")          # never inherit a stale lock
            time.sleep(0.05)
            player = StreamingPlayer(pcm_play, sr=SR, device_hint="Realtek",
                                     gain_db=args.gain_db)
            player.start()
            time.sleep(args.settle)

            dd.read_status(ser)
            ser.write(b"L")
            time.sleep(0.05)
            st_status = dd.read_status(ser)
            win = st_status["win"]
            # The completed window sits in the half the mel engine selected:
            # before the 2026-11-13 win_base fix it latched win_id[0] (already
            # the NEXT window id, i.e. the half being overwritten); after the
            # fix it latches ~win_id[0].  --half picks the right one, --half
            # both reads and scores both so the two bitstreams are directly
            # comparable.
            if args.half == "both":
                halves = [0, 1]
            elif args.half == "prev":
                halves = [0 if (win & 1) else 1]
            else:
                halves = [win & 1]
            t0 = time.time()
            pcms = {}
            for h in halves:
                pcms[h] = read_ddr_robust(ser, dd.PCM_LASE + dd.PCM_WIN_STRIDE * h,
                                          dd.PCM_WIN_BYTES, progress=True)
            spec_raw = read_ddr_robust(ser, SPEC_BASE, SPEC_BYTES)
            print("    read %d B in %.1f s" % (len(spec_raw) + sum(len(v) for v in pcms.values()),
                                               time.time() - t0), flush=True)
            logits = dd.read_logits(ser)
            ser.write(b"U")
            time.sleep(0.05)
        finally:
            if player is not None:
                player.stop()
            ser.close()

        board_db = np.frombuffer(spec_raw, dtype="<i2").astype(np.int16)
        board_db = board_db.reshape(N_FRAMES, N_MELS).T.copy()   # (64, 258)

        stats = None
        gold_db = None
        pcm_best = None
        g_best = None
        for h, raw in pcms.items():
            pcm = np.frombuffer(raw, dtype="<i2").astype(np.int16)[:PCM_SAMPLES]
            g = gp.run_mel_pipeline(pcm, tables)
            g_db = g["dbspec"].astype(np.int16)
            diff = board_db.astype(np.int32) - g_db.astype(np.int32)
            live = (board_db > -20400) & (g_db > -20400)
            offset = int(np.median(diff[live])) if live.any() else 0
            resid = np.abs(diff[live] - offset) if live.any() else np.array([0])
            st = {
                "run": run,
                "half": h,
                "win": win,
                "status": st_status,
                "pcm_std": float(pcm.std()),
                "pcm_min": int(pcm.min()),
                "pcm_max": int(pcm.max()),
                "board_db_min": int(board_db.min()),
                "board_db_max": int(board_db.max()),
                "board_db_mean": float(board_db.mean()),
                "gold_db_min": int(g_db.min()),
                "gold_db_max": int(g_db.max()),
                "gold_db_mean": float(g_db.mean()),
                "diff_max_abs": int(np.abs(diff).max()),
                "diff_mean_abs": float(np.abs(diff).mean()),
                "exact_pct": float((diff == 0).mean() * 100.0),
                "corr": float(np.corrcoef(board_db.ravel(), g_db.ravel())[0, 1]),
                "offset_lsb": offset,
                "resid_max_abs": int(resid.max()),
                "resid_p995_abs": int(np.percentile(resid, 99.5)),
                "resid_mean_abs": float(resid.mean()),
                # Frames whose max residual exceeds 2 dB.  They used to
                # concentrate at the start of the window (the win_base race);
                # after the fix they should be zero.
                "bad_frames": int((np.abs(diff).max(0) > 512).sum()),
                "logits_int32": logits,
            }
            print("[run %d half %d] win=%d pcm std=%.1f  board dB [%d..%d] mean %.1f | "
                  "golden dB [%d..%d] mean %.1f" % (
                      run, h, win, st["pcm_std"],
                      st["board_db_min"], st["board_db_max"], st["board_db_mean"],
                      st["gold_db_min"], st["gold_db_max"], st["gold_db_mean"]))
            print("        raw: exact=%.2f%%  max|d|=%d  mean|d|=%.2f  corr=%.4f" % (
                st["exact_pct"], st["diff_max_abs"], st["diff_mean_abs"], st["corr"]))
            print("        after removing the %d LSB window constant: mean|d|=%.2f  "
                  "p99.5=%d  max=%d  (>2 dB frames: %d)"
                  % (offset, st["resid_mean_abs"], st["resid_p995_abs"],
                     st["resid_max_abs"], st["bad_frames"]))
            print("        logits=%s" % (logits,))
            if stats is None or st["bad_frames"] < stats["bad_frames"]:
                stats, gold_db, pcm_best, g_best = st, g_db, pcm, g
        if len(pcms) > 1:
            print("    best half = %d (%d bad frames)" % (stats["half"], stats["bad_frames"]))
        results.append((stats, board_db, gold_db, pcm_best, g_best))

    outdir = ROOT / "build" / "diag" / ("spec_" + args.label)
    outdir.mkdir(parents=True, exist_ok=True)
    first = results[0]
    np.save(outdir / "board_db.npy", first[1])
    np.save(outdir / "gold_db.npy", first[2])
    np.save(outdir / "pcm.npy", first[3])
    (outdir / "meta.json").write_text(json.dumps(
        {"label": args.label, "gain_db": args.gain_db, "freq": args.freq,
         "play": args.play, "runs": [r[0] for r in results]}, indent=2),
        encoding="utf-8")
    print("saved:", outdir)

    worst = max(r[0]["resid_p995_abs"] for r in results)
    return 0 if worst <= 8 else 1


if __name__ == "__main__":
    raise SystemExit(main())