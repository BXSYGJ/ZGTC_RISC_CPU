"""48 kHz front-end truth-chain self-check (MODEL_TRAINING_SPEC_20261104 2.1).

Purpose: validate the native-48 kHz Mel table set and golden pipeline
BEFORE the retrained model is delivered, so the FPGA-side contract
adaptation (spec appendix B step 1) can start from a frozen truth source.

Checked chain:
  1. Table set invariants: gen_mel_tables.py --sr 48000 --f-max 24000
     --suffix _48k produces scripts/outputs/mel_tables_48k.json (+
     mel_tables_48k.coe, mel_coo_48k.hex). hann_q15 / log2_lut / exp_lut
     are sampling-rate invariants -> their per-table sha256 equals the
     44.1 kHz production ones and the existing src/mel/hann_q15.hex /
     log2_lut.hex files decode to the same values (the 48k set REUSES
     those RTL files; only mel_coo differs: 1960 -> 1962 entries).
  2. Default regression: running the generator with no arguments is
     byte-identical to the frozen production tables, and the 44.1 kHz
     golden path reproduces scripts/outputs/golden/sine_440_full_feat.npy
     bit-exactly (zero default-path breakage).
  3. Golden pipeline on synthesized 48 kHz PCM (440 Hz full-scale sine,
     seeded white noise, multi-tone mix): feature geometry (64, 258)
     uint8, saturation behaviour and dynamic range sane (44.1 kHz
     post-fix reference: sine min 43 / max 121 / mean 48.6).
  4. librosa float semantic sanity: melspectrogram(sr=48000, fmax=24000)
     + power_to_db(ref=max, top_db=80) + tail-258 + per-sample
     standardization vs the integer pipeline's z/4096: global and
     per-mel-bin Pearson r (floor-only degenerate bins are excluded from
     the r assertion and covered by the max|delta| guard instead).
  5. hex <-> json cross-check: mel_coo_48k.hex (65 offset words + one
     27-bit entry word per line) decodes to exactly the COO data of
     mel_tables_48k.json.
  6. Determinism: re-running the pipeline and re-generating the tables
     reproduces identical hashes.

Report: reports/mel48k_truth_chain_20261104.json.

Usage (from instrec_fpga/):  python experiments/mel48k/run_check.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]          # instrec_fpga/
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gen_mel_tables as gmt   # noqa: E402 (path-injected module)
import golden_pipeline as gp   # noqa: E402 (path-injected module)

SR_48K = 48000
FMAX_48K = 24000.0
TABLES_48K = SCRIPTS_DIR / "outputs" / "mel_tables_48k.json"
COO_HEX_48K = SCRIPTS_DIR / "outputs" / "mel_coo_48k.hex"
TABLES_44K = SCRIPTS_DIR / "outputs" / "mel_tables.json"
COE_44K = SCRIPTS_DIR / "outputs" / "mel_tables.coe"
SRC_MEL = ROOT / "src" / "mel"
SINE_WAV_44K = ROOT / "tests" / "fixtures" / "sine_440_full.wav"
# Frozen post-fix 44.1 kHz golden reference (gen_golden_refs.py output;
# scripts/outputs/golden/ holds a stale placeholder-era archive instead,
# see tests/test_golden_refs.py).
FROZEN_FEAT_44K = ROOT / "reports" / "golden_ref" / "sine_440_full" / "feat.npy"
REPORT_PATH = ROOT / "reports" / "mel48k_truth_chain_20261104.json"

RNG_SEED = 20261104
N_FULL_SEC = 144000            # 3 s of audio at 48 kHz (pre-cut)
FULL_SCALE = 32767
SINE_FREQ = 440.0
MULTI_FREQS = (440.0, 1320.0, 3500.0)

# Acceptance thresholds (44.1 kHz post-fix domain semantics).
R_FLOOR = 0.99                 # Pearson r floor, global AND per active bin
MAX_ABS_DELTA = 0.05           # REQ-ACC-001 tolerance (normalized z domain)
DEGENERATE_BIN_STD = 1e-3      # floor-only mel bins: guarded by delta, not r
FEAT_DOMAIN_MAX = 177          # z Q4.12 rail +8 -> 8*15.94+49 (>>36 fix)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Synthesized 48 kHz test PCM (deterministic, hardware-window sized).
# ---------------------------------------------------------------------------
def synth_signals() -> dict[str, np.ndarray]:
    """Three deterministic 48 kHz tracks, cut to the hardware window.

    Each track is first built over a full 3 s (144000 samples @ 48 kHz)
    then cut to the 132096-sample hardware window (258 frames x 512),
    mirroring golden_pipeline.load_pcm_s16's windowing semantics.
    """
    t = np.arange(N_FULL_SEC, dtype=np.float64) / SR_48K
    sine = np.round(np.sin(2.0 * np.pi * SINE_FREQ * t) * FULL_SCALE)
    rng = np.random.default_rng(RNG_SEED)
    noise = rng.integers(-FULL_SCALE, FULL_SCALE + 1, size=N_FULL_SEC)
    mix = np.zeros(N_FULL_SEC, dtype=np.float64)
    for freq in MULTI_FREQS:
        mix += np.sin(2.0 * np.pi * freq * t)
    mix = np.round(mix / len(MULTI_FREQS) * FULL_SCALE)

    out = {}
    for name, sig in (("sine_440_full", sine), ("white_noise", noise),
                      ("multi_tone", mix)):
        out[name] = np.asarray(sig[: gp.WINDOW_SAMPLES], dtype=np.int16)
    return out


# ---------------------------------------------------------------------------
# librosa float-domain reference (features.py semantics at 48 kHz).
# ---------------------------------------------------------------------------
def librosa_ref_z(pcm: np.ndarray) -> np.ndarray:
    """Float Mel+dB+standardize reference on the 48 kHz domain.

    Chain mirrors InstRec/src/features.py extract_mel_waveform with the
    MODEL_TRAINING_SPEC_20261104 section 2.1 parameters: sr 48000,
    fmax 24000, n_fft 2048 / hop 512 / 64 slaney mels, power 2,
    power_to_db(ref=np.max, amin=1e-10, top_db=80), keep the TAIL 258
    frames, then per-sample zero-mean/unit-var standardization (eps 1e-6).
    """
    y = pcm.astype(np.float32) / np.float32(32768.0)
    mel_power = librosa.feature.melspectrogram(
        y=y, sr=SR_48K, n_fft=2048, hop_length=512, win_length=2048,
        window="hann", center=True, pad_mode="reflect",
        n_mels=64, fmin=0.0, fmax=FMAX_48K, power=2.0,
    )
    db = librosa.power_to_db(mel_power, ref=np.max, amin=1e-10, top_db=80.0)
    db = db[:, db.shape[1] - gp.N_FRAMES:]
    z = (db - db.mean()) / (db.std() + 1e-6)
    return z.astype(np.float32)                      # (64, 258)


def pearson_metrics(z_gold: np.ndarray, z_ref: np.ndarray) -> dict:
    """Global + per-mel-bin Pearson r and max|delta| vs the float reference.

    Floor-only bins (reference std below DEGENERATE_BIN_STD) carry no
    dynamic range, so their correlation coefficient is undefined; they
    are counted as 'degenerate_bins' and covered by the global
    max|delta| guard (both sides sit on the same top_db floor).
    """
    g = z_gold.astype(np.float64)
    r = z_ref.astype(np.float64)
    global_r = float(np.corrcoef(g.ravel(), r.ravel())[0, 1])
    max_abs_delta = float(np.max(np.abs(g - r)))

    per_bin = []
    n_degenerate = 0
    for ch in range(g.shape[0]):
        b = r[ch]
        if float(b.std()) < DEGENERATE_BIN_STD:
            n_degenerate += 1
            continue
        per_bin.append(float(np.corrcoef(g[ch], b)[0, 1]))
    return {
        "global_pearson_r": global_r,
        "per_bin_min_r": float(np.min(per_bin)),
        "per_bin_mean_r": float(np.mean(per_bin)),
        "per_bin_active_count": len(per_bin),
        "degenerate_bins": n_degenerate,
        "max_abs_delta": max_abs_delta,
    }


# ---------------------------------------------------------------------------
# COO hex parsing (RTL $readmemh carrier cross-check).
# ---------------------------------------------------------------------------
def parse_coo_hex(path: Path) -> tuple[list[int], list[tuple[int, int]]]:
    """Decode mel_coo.hex: 65 offset words + 27-bit entry words.

    Entry word layout (mel_filter.v TABLE FILES contract):
      {bin_idx[26:16] (11 bit), weight[15:0] (signed Q1.15)}.
    """
    words = [ln.strip() for ln in path.read_text("ascii").splitlines()
             if ln.strip()]
    offsets = [int(w, 16) for w in words[: gmt.COO_OFFSET_HEADER_LEN]]
    entries = []
    for w in words[gmt.COO_OFFSET_HEADER_LEN:]:
        v = int(w, 16)
        bin_idx = v >> 16
        w16 = v & 0xFFFF
        weight = w16 - 0x10000 if w16 >= 0x8000 else w16
        entries.append((bin_idx, weight))
    return offsets, entries


def parse_plain_hex(path: Path, signed: bool) -> list[int]:
    """Decode a plain one-word-per-line hex file (hann/log2 tables)."""
    vals = [int(ln.strip(), 16) for ln in path.read_text("ascii").splitlines()
            if ln.strip()]
    if signed:
        vals = [v - 0x10000 if v >= 0x8000 else v for v in vals]
    return vals


# ---------------------------------------------------------------------------
# Main check sequence.
# ---------------------------------------------------------------------------
def main() -> int:
    failures: list[str] = []

    def check(ok: bool, what: str) -> bool:
        if not ok:
            failures.append(what)
        return ok

    tables_48k = gp.load_mel_tables(TABLES_48K)
    params_48k = tables_48k["params"]
    check(params_48k["sr"] == SR_48K, "table params.sr == 48000")
    check(params_48k["f_max"] == FMAX_48K, "table params.f_max == 24000")

    payload_48k = json.loads(TABLES_48K.read_text("ascii"))
    payload_44k = json.loads(TABLES_44K.read_text("ascii"))
    t48 = payload_48k["tables"]
    t44 = payload_44k["tables"]

    # ---- 1. invariant tables identical between the two domains ----------
    invariants = {
        "hann_q15_sha256_44k_eq_48k": (
            t44["hann_q15"]["sha256"] == t48["hann_q15"]["sha256"]),
        "log2_lut_sha256_44k_eq_48k": (
            t44["log2_lut"]["sha256"] == t48["log2_lut"]["sha256"]),
        "exp_lut_sha256_44k_eq_48k": (
            t44["exp_lut"]["sha256"] == t48["exp_lut"]["sha256"]),
        "mel_coo_sha256_44k": t44["mel_coo"]["sha256"],
        "mel_coo_sha256_48k": t48["mel_coo"]["sha256"],
        "mel_coo_entries_44k": t44["mel_coo"]["n_entries"],
        "mel_coo_entries_48k": t48["mel_coo"]["n_entries"],
        "mel_coo_bin_min_48k": int(min(t48["mel_coo"]["bin_idx"])),
        "mel_coo_bin_max_48k": int(max(t48["mel_coo"]["bin_idx"])),
    }
    check(invariants["hann_q15_sha256_44k_eq_48k"], "hann table invariant")
    check(invariants["log2_lut_sha256_44k_eq_48k"], "log2 table invariant")
    check(invariants["exp_lut_sha256_44k_eq_48k"], "exp table invariant")
    check(t44["mel_coo"]["sha256"] != t48["mel_coo"]["sha256"],
          "mel_coo actually differs between domains")

    # The production src/mel hex files decode to the 48k table values, so
    # the 48k RTL injection REUSES src/mel/hann_q15.hex + log2_lut.hex and
    # only swaps the COO image (mel_coo_48k.hex).
    hann_hex = parse_plain_hex(SRC_MEL / "hann_q15.hex", signed=True)
    log2_hex = parse_plain_hex(SRC_MEL / "log2_lut.hex", signed=False)
    invariants["src_mel_hann_hex_matches_48k_table"] = (
        hann_hex == t48["hann_q15"]["data"])
    invariants["src_mel_log2_hex_matches_48k_table"] = (
        log2_hex == t48["log2_lut"]["data"])
    check(invariants["src_mel_hann_hex_matches_48k_table"],
          "src/mel/hann_q15.hex == 48k hann table")
    check(invariants["src_mel_log2_hex_matches_48k_table"],
          "src/mel/log2_lut.hex == 48k log2 table")

    # ---- 2. default-path regression --------------------------------------
    tmp = Path(tempfile.mkdtemp())
    try:
        gmt.main(["--outdir", str(tmp)])
        default_json_hash = _sha256_file(tmp / "mel_tables.json")
        default_coe_hash = _sha256_file(tmp / "mel_tables.coe")
        frozen_json_hash = _sha256_file(TABLES_44K)
        frozen_coe_hash = _sha256_file(COE_44K)
        check(default_json_hash == frozen_json_hash,
              "default generator run byte-identical to mel_tables.json")
        check(default_coe_hash == frozen_coe_hash,
              "default generator run byte-identical to mel_tables.coe")

        # COO hex layout fidelity: the 44.1k values under a suffix must
        # byte-match the RTL production file src/mel/mel_coo.hex.
        gmt.main(["--outdir", str(tmp), "--suffix", "_layout"])
        layout_hash = _sha256_file(tmp / "mel_coo_layout.hex")
        production_coo_hash = _sha256_file(SRC_MEL / "mel_coo.hex")
        check(layout_hash == production_coo_hash,
              "write_coo_hex layout byte-identical to src/mel/mel_coo.hex")

        # 48k table regeneration determinism (same CLI, fresh output dir).
        gmt.main(["--outdir", str(tmp), "--sr", "48000",
                  "--f-max", "24000", "--suffix", "_48k"])
        regen_json = _sha256_file(tmp / "mel_tables_48k.json")
        regen_hex = _sha256_file(tmp / "mel_coo_48k.hex")
        regen_coe = _sha256_file(tmp / "mel_tables_48k.coe")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---- 3/4. golden pipeline on synthesized 48 kHz PCM -------------------
    signals = synth_signals()
    sanity = {}
    for name, pcm in signals.items():
        res = gp.run_mel_pipeline(pcm, tables_48k)
        feat = res["feat"]
        entry = {
            "feat_shape": list(feat.shape),
            "feat_dtype": str(feat.dtype),
            "feat_min": int(feat.min()),
            "feat_max": int(feat.max()),
            "feat_mean": round(float(feat.mean()), 4),
            "feat_std": round(float(feat.std()), 4),
            "sat_0_count": int((feat == 0).sum()),
            "sat_255_count": int((feat == 255).sum()),
            "feat_sha256": _sha256_bytes(feat.tobytes()),
        }
        check(feat.shape == (64, 258) and feat.dtype == np.uint8,
              f"{name}: feature geometry (64, 258) uint8")
        check(entry["sat_255_count"] == 0, f"{name}: no upper-rail saturation")
        check(entry["feat_max"] <= FEAT_DOMAIN_MAX,
              f"{name}: feat max within the >>36-fix domain bound 177")
        if name == "sine_440_full":
            # The 44.1 kHz post-fix reference track: no saturation at all
            # and a healthy dynamic range (reference min 43 / max 121 /
            # mean 48.6; the 48k filterbank widens the spectrum so the
            # bounds are relaxed accordingly).
            check(entry["sat_0_count"] == 0, "sine: no lower-rail saturation")
            check(20 <= entry["feat_min"] and entry["feat_max"] <= 177,
                  "sine: dynamic range sane")
            check(40.0 <= entry["feat_mean"] <= 60.0, "sine: mean sane")
        check(entry["feat_std"] > 5.0, f"{name}: feature not degenerate")

        z_gold = res["z"].astype(np.float64) / 4096.0
        z_ref = librosa_ref_z(pcm)
        m = pearson_metrics(z_gold, z_ref)
        entry["librosa"] = m
        check(m["global_pearson_r"] > R_FLOOR,
              f"{name}: global Pearson r > {R_FLOOR}")
        check(m["per_bin_min_r"] > R_FLOOR,
              f"{name}: per-active-bin Pearson r > {R_FLOOR}")
        check(m["max_abs_delta"] <= MAX_ABS_DELTA,
              f"{name}: max|delta| <= {MAX_ABS_DELTA}")
        sanity[name] = entry

    # ---- 5. hex <-> json COO cross-check ----------------------------------
    offsets, entries = parse_coo_hex(COO_HEX_48K)
    coo = t48["mel_coo"]
    hex_lines = [ln for ln in COO_HEX_48K.read_text("ascii").splitlines()
                 if ln.strip()]
    crosscheck = {
        "hex_total_lines": len(hex_lines),
        "expected_lines": gmt.COO_OFFSET_HEADER_LEN + coo["n_entries"],
        "offsets_match": offsets == coo["offsets"],
        "bin_idx_match": [e[0] for e in entries] == coo["bin_idx"],
        "weight_q15_match": [e[1] for e in entries] == coo["weight_q15"],
    }
    check(crosscheck["hex_total_lines"] == crosscheck["expected_lines"],
          "mel_coo_48k.hex line count")
    check(crosscheck["offsets_match"], "mel_coo_48k.hex offsets == json")
    check(crosscheck["bin_idx_match"], "mel_coo_48k.hex bin_idx == json")
    check(crosscheck["weight_q15_match"], "mel_coo_48k.hex weights == json")

    # ---- 6. pipeline re-run determinism -----------------------------------
    res_again = gp.run_mel_pipeline(signals["sine_440_full"], tables_48k)
    rerun_hash = _sha256_bytes(res_again["feat"].tobytes())
    rerun_ok = rerun_hash == sanity["sine_440_full"]["feat_sha256"]
    check(rerun_ok, "pipeline re-run reproduces the feature hash")
    regen_ok = (regen_json == _sha256_file(TABLES_48K)
                and regen_hex == _sha256_file(COO_HEX_48K))
    check(regen_ok, "table regeneration reproduces file hashes")

    # ---- extra: 44.1 kHz golden path frozen-output identity --------------
    tables_44k = gp.load_mel_tables(TABLES_44K)
    pcm_44k = gp.load_pcm_s16(SINE_WAV_44K)          # default sr = SR (44100)
    res_44k = gp.run_mel_pipeline(pcm_44k, tables_44k)
    frozen = np.load(FROZEN_FEAT_44K)
    frozen_ok = bool(np.array_equal(res_44k["feat"], frozen))
    check(frozen_ok, "44.1k golden sine feat == frozen golden ref")

    # ---- report ------------------------------------------------------------
    report = {
        "report": "mel48k_truth_chain_20261104",
        "date": "2026-11-04",
        "spec_refs": ("MODEL_TRAINING_SPEC_20261104 section 2.1 (F1 native "
                      "48 kHz front-end); spec appendix B step 1"),
        "generator_cli": ("python scripts/gen_mel_tables.py --sr 48000 "
                          "--f-max 24000 --suffix _48k"),
        "default_regression": {
            "mel_tables_json_sha256": frozen_json_hash,
            "mel_tables_coe_sha256": frozen_coe_hash,
            "generator_default_byte_identical": default_json_hash == frozen_json_hash
            and default_coe_hash == frozen_coe_hash,
            "coo_hex_layout_matches_src_mel_mel_coo_hex": layout_hash
            == production_coo_hash,
            "golden_44k_sine_feat_identical_to_frozen_ref": frozen_ok,
        },
        "tables_48k": {
            "mel_tables_48k_json": {
                "sha256": _sha256_file(TABLES_48K),
                "bytes": TABLES_48K.stat().st_size,
            },
            "mel_tables_48k_coe": {
                "sha256": _sha256_file(SCRIPTS_DIR / "outputs"
                                       / "mel_tables_48k.coe"),
            },
            "mel_coo_48k_hex": {
                "sha256": _sha256_file(COO_HEX_48K),
                "bytes": COO_HEX_48K.stat().st_size,
                "lines": len(hex_lines),
                "entries": coo["n_entries"],
            },
            "invariants": invariants,
            "rtl_injection": {
                "reuse": ["src/mel/hann_q15.hex", "src/mel/log2_lut.hex",
                          "src/mel/exp_lut.hex"],
                "swap": "src/mel/mel_coo.hex <- scripts/outputs/"
                        "mel_coo_48k.hex (future model delivery; COO_HEX_FILE"
                        " parameter of mel_engine/mel_filter is the"
                        " injection point)",
                "note": ("mel_engine.v already exposes HAN_HEX_FILE / "
                         "COO_HEX_FILE / LUT_HEX_FILE parameters, so the "
                         "48k swap is an instantiation-level change; this "
                         "run leaves src/ untouched per task constraints"),
            },
        },
        "sanity": sanity,
        "thresholds": {
            "pearson_r_floor": R_FLOOR,
            "max_abs_delta": MAX_ABS_DELTA,
            "feat_domain_max": FEAT_DOMAIN_MAX,
            "degenerate_bin_std": DEGENERATE_BIN_STD,
        },
        "hex_json_crosscheck": crosscheck,
        "repeat_run": {
            "pipeline_feat_sha256_reproduced": rerun_ok,
            "table_regen_hashes_reproduced": regen_ok,
            "mel_tables_48k_json_sha256": regen_json,
            "mel_coo_48k_hex_sha256": regen_hex,
            "mel_tables_48k_coe_sha256": regen_coe,
        },
        "failures": failures,
        "conclusion": "PASS" if not failures else f"FAIL ({len(failures)} checks)",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="ascii", newline="\n") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=True)
        fh.write("\n")

    for name, entry in sanity.items():
        m = entry["librosa"]
        print(f"[mel48k] {name}: feat min/max/mean = "
              f"{entry['feat_min']}/{entry['feat_max']}/{entry['feat_mean']}, "
              f"sat0/sat255 = {entry['sat_0_count']}/{entry['sat_255_count']}")
        print(f"[mel48k] {name}: librosa r global {m['global_pearson_r']:.6f} "
              f"per-bin min {m['per_bin_min_r']:.6f} (active "
              f"{m['per_bin_active_count']}, degenerate "
              f"{m['degenerate_bins']}), max|d| {m['max_abs_delta']:.4f}")
    print(f"[mel48k] hex<->json crosscheck: {crosscheck}")
    print(f"[mel48k] default regression: {report['default_regression']}")
    print(f"[mel48k] conclusion: {report['conclusion']}")
    print(f"[mel48k] report: {REPORT_PATH}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
