#!/usr/bin/env python3
"""Compare a board diag_dump capture against the 48 kHz golden pipeline.

The board half is scripts/diag_dump.py: it locks a completed window and pulls
back three artefacts into build/diag/<label>/win<NNNN>/:

    pcm.raw      264,192 B   132,096 x int16, LEFT channel, little endian
                             (the exact PCM the mel_engine consumed)
    feat.bin     16,512 B    64 x 258 uint8, mel-major order (mel*258 + frame)
                             -> only valid when FEAT_DUMP_ON_M3 == 1, otherwise
                                it holds stale/dB-spectrum bytes and is skipped
    logits.json  logits_int32: [8 x int32], the npu_top 'G' readback

This script re-runs the bit-accurate golden model (golden_pipeline.py) on the
SAME PCM the board consumed, so every difference isolates a real RTL defect:

    feat    golden.run_mel_pipeline(pcm)   vs board feat.bin  -> mel engine
    logits  golden.npu_forward(feat)       vs board logits    -> NPU

The comparison is self-consistent: it does NOT re-read the wav, so a channel
or windowing difference between the host and the board cannot be mistaken for
a mel/NPU arithmetic bug.  The PCM statistics (std/min/max) are printed first
because the whole 48 kHz bring-up began with "the window content is constant":
if pcm.raw does not change across the four experiments the defect is upstream
of the Mel engine, and every downstream byte-exact check is moot.

Exit codes: 0 = all available artefacts match, 1 = any mismatch, 2 = usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

import golden_pipeline as gp

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent

TABLES_48K = SCRIPTS / "outputs" / "mel_tables_48k.json"
CONTRACT_48K = SCRIPTS / "outputs" / "medley_48k" / "layer_contract.json"
WEIGHTS_48K = SCRIPTS / "outputs" / "medley_48k" / "weights_image.bin"

PCM_SAMPLES = 132096
FEAT_SHAPE = (64, 258)
FEAT_BYTES = FEAT_SHAPE[0] * FEAT_SHAPE[1]


def load_diag_dir(diag_dir: Path) -> dict:
    """Load pcm.raw / feat.bin / logits.json from one win<NNNN> capture."""
    pcm_path = diag_dir / "pcm.raw"
    feat_path = diag_dir / "feat.bin"
    logits_path = diag_dir / "logits.json"

    pcm = np.frombuffer(pcm_path.read_bytes(), dtype="<i2").astype(np.int16)
    if pcm.size < PCM_SAMPLES:
        raise ValueError(f"{pcm_path}: only {pcm.size} samples, "
                         f"expected >= {PCM_SAMPLES}")
    pcm = pcm[:PCM_SAMPLES].copy()

    feat = np.frombuffer(feat_path.read_bytes(), dtype=np.uint8)
    feat_ok = feat.size == FEAT_BYTES

    logits = None
    if logits_path.is_file():
        logits = json.loads(logits_path.read_text(encoding="utf-8"))
        logits = np.asarray(logits["logits_int32"], dtype=np.int32)

    return {
        "pcm": pcm,
        "feat": feat.reshape(FEAT_SHAPE) if feat_ok else None,
        "feat_bytes": int(feat.size),
        "logits": logits,
    }


def report_pcm(pcm: np.ndarray) -> dict:
    a = pcm.astype(np.int64)
    return {
        "std": float(a.std()),
        "min": int(a.min()),
        "max": int(a.max()),
        "abs_mean": float(np.abs(a).mean()),
        "n_nonzero": int(np.count_nonzero(a)),
    }


def compare_feat(golden: np.ndarray, board: np.ndarray) -> dict:
    gf = golden.reshape(-1)
    bf = board.reshape(-1)
    if bf.size != gf.size:
        return {"ok": False, "reason": f"size {bf.size} != {gf.size}"}
    diff = bf.astype(np.int64) - gf.astype(np.int64)
    n = int(np.count_nonzero(diff))
    first = None
    if n:
        i = int(np.argmax(diff != 0))
        first = {
            "mel": i // FEAT_SHAPE[1],
            "frame": i % FEAT_SHAPE[1],
            "got": int(bf[i]),
            "expected": int(gf[i]),
        }
    return {
        "ok": n == 0,
        "different_bytes": n,
        "max_abs_diff": int(np.abs(diff).max()),
        "first": first,
    }


def compare_logits(golden: np.ndarray, board: np.ndarray) -> dict:
    if board.size != golden.size:
        return {"ok": False, "reason": f"size {board.size} != {golden.size}"}
    diff = board.astype(np.int64) - golden.astype(np.int64)
    return {
        "ok": bool(np.array_equal(board, golden)),
        "max_abs_diff": int(np.abs(diff).max()),
        "golden": golden.tolist(),
        "board": board.tolist(),
        "golden_top1": int(np.argmax(golden)),
        "board_top1": int(np.argmax(board)),
    }


def discover_latest(diag_root: Path, label: str) -> Path:
    """Pick the highest-numbered win<NNNN> dir under build/diag/<label>."""
    label_dir = diag_root / label
    wins = sorted(label_dir.glob("win*"), key=lambda p: p.name)
    if not wins:
        raise FileNotFoundError(f"no win* capture under {label_dir}")
    return wins[-1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=None,
                    help="explicit win<NNNN> capture directory")
    ap.add_argument("--label", default=None,
                    help="label under build/diag/ (uses the latest win*)")
    ap.add_argument("--json", type=Path, default=None,
                    help="write the comparison evidence to this path")
    ap.add_argument("--skip-feat", action="store_true",
                    help="skip the feat comparison (FEAT_DUMP_ON_M3 == 0)")
    args = ap.parse_args(argv)

    if args.dir is None and args.label is None:
        print("error: give --dir or --label", file=sys.stderr)
        return 2
    diag_dir = args.dir.resolve() if args.dir else \
        discover_latest(ROOT / "build" / "diag", args.label)
    if not diag_dir.is_dir():
        print(f"error: {diag_dir} is not a directory", file=sys.stderr)
        return 2

    try:
        cap = load_diag_dir(diag_dir)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    tables = gp.load_mel_tables(TABLES_48K)
    contract = gp.load_layer_contract(CONTRACT_48K)
    weights = gp.load_weights_from_image(contract, WEIGHTS_48K)

    pcm_stats = report_pcm(cap["pcm"])
    mel = gp.run_mel_pipeline(cap["pcm"], tables,
                              inv_s_in=236403274, zp_in=47)
    golden_feat = mel["feat"]                       # (64, 258) uint8
    npu = gp.npu_forward(golden_feat, contract, tables["exp_lut"], weights)
    golden_logits = np.asarray(npu["logits"], dtype=np.int32)

    print(f"capture        : {diag_dir}")
    print(f"pcm            : std={pcm_stats['std']:.1f} "
          f"min={pcm_stats['min']} max={pcm_stats['max']} "
          f"abs_mean={pcm_stats['abs_mean']:.1f} "
          f"nonzero={pcm_stats['n_nonzero']}/{pcm_stats['n_nonzero'] and PCM_SAMPLES}")

    results = {"pcm": pcm_stats}

    if cap["feat"] is not None and not args.skip_feat:
        fr = compare_feat(golden_feat, cap["feat"])
        results["feat"] = fr
        if fr["first"]:
            f = fr["first"]
            print(f"feat           : {'MATCH' if fr['ok'] else 'MISMATCH'} "
                  f"{fr['different_bytes']} byte(s) differ, "
                  f"first at mel {f['mel']} frame {f['frame']} "
                  f"got {f['got']} expected {f['expected']}")
        else:
            print(f"feat           : {'MATCH' if fr['ok'] else fr.get('reason')} "
                  f"({fr['different_bytes']} byte(s) differ)")
    else:
        print(f"feat           : SKIPPED (feat_bytes={cap['feat_bytes']}, "
              f"FEAT_DUMP_ON_M3 presumed 0)")

    if cap["logits"] is not None:
        lr = compare_logits(golden_logits, cap["logits"])
        results["logits"] = lr
        print(f"logits         : {'MATCH' if lr['ok'] else 'MISMATCH'} "
              f"max|d|={lr['max_abs_diff']} "
              f"golden_top1={lr['golden_top1']} board_top1={lr['board_top1']}")
        print(f"  golden       : {lr['golden']}")
        print(f"  board        : {lr['board']}")
    else:
        print("logits         : SKIPPED (no logits.json)")

    ok = True
    if "feat" in results and not results["feat"]["ok"]:
        ok = False
    if "logits" in results and not results["logits"]["ok"]:
        ok = False

    if args.json:
        target = args.json
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "capture": str(diag_dir),
            "ok": ok,
            "results": results,
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True),
                          encoding="utf-8", newline="\n")
        print(f"evidence       : {target}")

    print(f"RESULT         : {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
