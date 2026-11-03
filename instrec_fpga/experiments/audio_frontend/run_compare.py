"""Run the F0/F1/F2/F2b front-end comparison and emit the JSON report.

Usage (from instrec_fpga/):

    python experiments/audio_frontend/run_compare.py
    python experiments/audio_frontend/run_compare.py --wav path/to/x.wav
    python experiments/audio_frontend/run_compare.py --out reports/foo.json

Default behaviour: three seeded synthetic signals (48 kHz domain), the
three board fixtures (tests/fixtures/*.wav, up-sampled 44.1k -> 48k) and
eight real instrument demo clips (InstRec/data/demo/irmas_test/*.wav,
read-only) are pushed through all four front-end variants; each variant's
feature is compared against F0 (per-bin difference statistics) and pushed
through three reference models to quantify the logits drift:

  8q  : the deployed quantized 8-class TorchScript (InstRec/deploy/
        quantized_model.pt) fed with the uint8 NPU input image
        (layer_contract.json quant stub: s_in, zp_in);
  8f  : the float 8-class checkpoint (InstRec/runs/best_model.pt,
        InstrumentCNN) fed with the float feature;
  g5  : the frozen 5-group float model (instrec_fpga/models/
        group5_v3_float_20261102, DualHeadInstrumentCNN) fed with the
        last-130-frame (1.5 s contract) tail of the float feature.

Three sanity checks gate the run:
  S1  the F0 Mel filterbank regenerated here matches the production
      mel_tables.json COO table (within the known sparsify drop);
  S2  the F0 float chain matches InstRec/src/features.py bit-near;
  S3  quantize_uint8 matches torch.quantize_per_tensor bit-exact.

The report contains no wall-clock timestamp so repeated runs are
byte-identical (determinism contract).

Read-only with respect to everything outside experiments/audio_frontend/
and reports/audio_frontend_comparison_20261104.json.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import frontend_variants as fv  # noqa: E402

PROJ = HERE.parents[1]                       # instrec_fpga/
PANGO = HERE.parents[3]                      # .../Pango/
INSTREC = PANGO / "InstRec"                  # read-only model source repo

DEFAULT_REPORT = PROJ / "reports" / "audio_frontend_comparison_20261104.json"
SEED = 20261104
INPUT_SECONDS = 3.0                          # 3 s windows, like the fixtures

# Read-only asset inventory (path, role). Hashed and recorded in the report.
ASSET_FILES = [
    (PROJ / "scripts" / "golden_pipeline.py", "bit-accurate F0 golden truth (8-class)"),
    (PROJ / "scripts" / "golden_pipeline_group5.py", "bit-accurate group5 golden truth"),
    (PROJ / "scripts" / "outputs" / "layer_contract.json", "quantization contract (s_in/zp_in, NPU weights image)"),
    (PROJ / "scripts" / "outputs" / "mel_tables.json", "production F0 Mel/Hann/log2 tables"),
    (PROJ / "models" / "group5_v3_float_20261102" / "float_state.npz", "frozen group5 v3 float weights"),
    (PROJ / "models" / "group5_v3_float_20261102" / "model_source.py", "group5 v3 model definition"),
    (PROJ / "models" / "group5_v3_float_20261102" / "manifest.json", "group5 v3 freeze manifest"),
    (INSTREC / "deploy" / "quantized_model.pt", "deployed 8-class quantized TorchScript"),
    (INSTREC / "runs" / "best_model.pt", "8-class float checkpoint (InstrumentCNN)"),
    (INSTREC / "runs" / "group5_v3" / "best_model.pth", "group5 v3 source checkpoint"),
    (INSTREC / "src" / "features.py", "production float feature reference"),
    (INSTREC / "src" / "model.py", "InstrumentCNN / DualHeadInstrumentCNN definition"),
]

FIXTURE_WAVS = [
    PROJ / "tests" / "fixtures" / "sine_440_full.wav",
    PROJ / "tests" / "fixtures" / "sine_440_twolevel.wav",
    PROJ / "tests" / "fixtures" / "silence_3s.wav",
]

REAL_WAVS = [
    INSTREC / "data" / "demo" / "irmas_test" / f"{name}_sample.wav"
    for name in (
        "clarinet", "flute", "guitar_acoustic", "guitar_electric",
        "piano", "saxophone", "trumpet", "violin",
    )
]

# The 8 production classes (layer_contract.json). The demo clips marked
# with None have no exact match in the demo set (recorded as data gap).
REAL_WAV_CLASS = {
    "clarinet": "clarinet",
    "flute": "flute",
    "guitar_acoustic": None,          # not in the 8 production classes
    "guitar_electric": None,          # closest to distorted electric guitar
    "piano": "piano",
    "saxophone": "tenor saxophone",   # family match
    "trumpet": "trumpet",
    "violin": "violin",
}

CLASS_NAMES = [
    "clarinet", "distorted electric guitar", "female singer", "flute",
    "piano", "tenor saxophone", "trumpet", "violin",
]
GROUP_NAMES = ["strings", "woodwinds", "brass", "percussion", "keys"]


# ---------------------------------------------------------------------------
# Small helpers.
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def safe_pearson(a: np.ndarray, b: np.ndarray):
    """Pearson r, None when either side is constant (e.g. silence)."""
    a = np.asarray(a, np.float64).ravel()
    b = np.asarray(b, np.float64).ravel()
    if a.std() < 1e-12 or b.std() < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def load_wav_48k(path: Path) -> np.ndarray:
    """Read a WAV and bring it to the 48 kHz front-end domain (mono, soxr)."""
    import librosa

    y, sr = librosa.load(str(path), sr=fv.INPUT_SR, mono=True, dtype=np.float32)
    return y, int(sr)


def import_module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Sanity checks.
# ---------------------------------------------------------------------------
def rebuild_mel_from_tables(tables_path: Path) -> np.ndarray:
    with open(tables_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    coo = payload["tables"]["mel_coo"]
    n_mels = payload["params"]["n_mels"]
    n_bins = payload["params"]["n_fft"] // 2 + 1
    dense = np.zeros((n_mels, n_bins))
    channels = np.asarray(coo["channels"])
    bin_idx = np.asarray(coo["bin_idx"])
    weights = np.asarray(coo["weight_q15"], np.float64) / 32768.0
    dense[channels, bin_idx] = weights
    return dense


def run_sanity_checks(quant: dict) -> dict:
    import librosa
    import torch

    results = {}

    # S1: F0 Mel filterbank vs production mel_tables.json.
    dense = rebuild_mel_from_tables(
        PROJ / "scripts" / "outputs" / "mel_tables.json"
    )
    lib = fv.mel_filterbank(44100, 2048, 22050.0)
    s1_max = float(np.abs(dense - lib).max())
    results["S1_mel_table_match"] = {
        "description": "regenerated F0 slaney Mel vs mel_tables.json COO rebuild",
        "max_abs_diff": s1_max,
        "pass": bool(s1_max <= 2e-4),
        "note": "gen_mel_tables.py drops COO entries with weight < 1e-4, "
                "so up to ~1e-4 difference per dropped entry is expected",
    }

    # S2: F0 float chain vs InstRec/src/features.py on the board fixture.
    features = import_module_from(INSTREC / "src" / "features.py",
                                  "instrec_features")
    y441, _ = librosa.load(str(FIXTURE_WAVS[0]), sr=44100, mono=True,
                           dtype=np.float32)
    ref = features.extract_mel_waveform(y441)
    mine = fv.run_frontend(None, "F0", y_native=y441)["z"]
    s2_max = float(np.abs(ref - mine).max())
    results["S2_features_py_match"] = {
        "description": "F0 float chain vs features.py extract_mel_waveform "
                       "on tests/fixtures/sine_440_full.wav",
        "max_abs_diff": s2_max,
        "pass": bool(s2_max <= 1e-4),
    }

    # S3: quantize_uint8 vs torch.quantize_per_tensor.
    s_in = float(quant["s_in"])
    zp_in = int(quant["zp_in"])
    z = mine
    u8_np = fv.quantize_uint8(z, s_in, zp_in)
    xq = torch.quantize_per_tensor(
        torch.tensor(z[None, None]), s_in, zp_in, torch.quint8)
    u8_t = xq.int_repr().numpy()[0, 0]
    n_mismatch = int((u8_np != u8_t).sum())
    results["S3_quantize_match"] = {
        "description": "frontend_variants.quantize_uint8 vs "
                       "torch.quantize_per_tensor (fbgemm round-half-even)",
        "mismatched_elements": n_mismatch,
        "total_elements": int(u8_np.size),
        "pass": bool(n_mismatch == 0),
    }

    results["all_pass"] = bool(all(
        v["pass"] for k, v in results.items() if isinstance(v, dict)
    ))
    return results


# ---------------------------------------------------------------------------
# Input signal construction (all in the 48 kHz front-end domain).
# ---------------------------------------------------------------------------
def synth_inputs() -> list:
    n = int(INPUT_SECONDS * fv.INPUT_SR)
    t = np.arange(n, dtype=np.float64) / fv.INPUT_SR
    rng = np.random.default_rng(SEED)

    sine = (0.5 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    noise = rng.normal(0.0, 0.1, n).astype(np.float32)
    noise2 = rng.normal(0.0, 1.0, n).astype(np.float32)
    multi = (
        0.30 * np.sin(2.0 * np.pi * 440.0 * t)
        + 0.25 * np.sin(2.0 * np.pi * 880.0 * t)
        + 0.20 * np.sin(2.0 * np.pi * 1320.0 * t)
        + 0.05 * noise2
    ).astype(np.float32)

    return [
        {"name": "synth_sine440", "kind": "synthetic",
         "detail": "440 Hz sine, amplitude 0.5, seed %d" % SEED,
         "pcm48": sine},
        {"name": "synth_white_noise", "kind": "synthetic",
         "detail": "Gaussian white noise, sigma 0.1, seed %d" % SEED,
         "pcm48": noise},
        {"name": "synth_multitone", "kind": "synthetic",
         "detail": "440+880+1320 Hz mix (0.30/0.25/0.20) + 0.05 noise",
         "pcm48": multi},
    ]


def wav_inputs(extra_wavs: list) -> list:
    out = []
    for path in FIXTURE_WAVS:
        y, _ = load_wav_48k(path)
        out.append({
            "name": "fixture_" + path.stem,
            "kind": "board_fixture",
            "detail": str(path.relative_to(PROJ)) + " (44.1k stereo-free "
                      "s16, up-sampled to 48k soxr_hq)",
            "pcm48": y,
            "path": str(path.relative_to(PROJ)),
        })
    for path in REAL_WAVS:
        key = path.stem.replace("_sample", "")
        y, _ = load_wav_48k(path)
        out.append({
            "name": "real_" + key,
            "kind": "real_instrument_demo",
            "detail": str(path) + " (44.1k stereo, mono-mixed + "
                      "up-sampled to 48k soxr_hq)",
            "pcm48": y,
            "path": str(path),
            "production_class": REAL_WAV_CLASS.get(key),
        })
    for path in extra_wavs:
        y, _ = load_wav_48k(Path(path))
        out.append({
            "name": "user_" + Path(path).stem,
            "kind": "user_wav",
            "detail": str(path),
            "pcm48": y,
            "path": str(path),
        })
    return out


# ---------------------------------------------------------------------------
# Model wrappers.
# ---------------------------------------------------------------------------
def load_models() -> dict:
    import torch

    torch.set_num_threads(1)
    models = {}

    # 8q: deployed quantized TorchScript (chained forward, golden parity).
    try:
        m = torch.jit.load(str(INSTREC / "deploy" / "quantized_model.pt"),
                           map_location="cpu")
        m.eval()
        models["8q"] = m
    except Exception as exc:  # noqa: BLE001
        models["8q"] = None
        models["8q_error"] = repr(exc)

    # 8f: float checkpoint + InstrumentCNN definition.
    try:
        model_mod = import_module_from(INSTREC / "src" / "model.py",
                                       "instrec_model")
        m = model_mod.InstrumentCNN(num_classes=8)
        ckpt = torch.load(str(INSTREC / "runs" / "best_model.pt"),
                          map_location="cpu", weights_only=False)
        state = ckpt["model_state_dict"] if "model_state_dict" in ckpt else ckpt
        state = { (k[7:] if k.startswith("module.") else k): v
                  for k, v in state.items() }
        m.load_state_dict(state, strict=True)
        m.eval()
        models["8f"] = m
    except Exception as exc:  # noqa: BLE001
        models["8f"] = None
        models["8f_error"] = repr(exc)

    # g5: frozen group5 v3 float model (DualHeadInstrumentCNN).
    try:
        g5_dir = PROJ / "models" / "group5_v3_float_20261102"
        g5_mod = import_module_from(g5_dir / "model_source.py",
                                    "group5_model_source")
        m = g5_mod.DualHeadInstrumentCNN(num_classes=5)
        state_np = np.load(str(g5_dir / "float_state.npz"))
        state = {k: torch.from_numpy(np.asarray(state_np[k]))
                 for k in state_np.files}
        m.load_state_dict(state, strict=True)
        m.eval()
        models["g5"] = m
    except Exception as exc:  # noqa: BLE001
        models["g5"] = None
        models["g5_error"] = repr(exc)

    return models


def infer_8q(model, u8: np.ndarray, s_in: float, zp_in: int) -> dict:
    """Chained quantized forward, identical to golden_pipeline.py
    torch_npu_reference (fed with the SAME uint8 feature)."""
    import torch

    xf = (torch.tensor(u8.astype(np.float32)) - zp_in) * s_in
    xq = torch.quantize_per_tensor(
        xf.unsqueeze(0).unsqueeze(0), s_in, zp_in, torch.quint8)
    assert torch.equal(
        xq.int_repr().squeeze(0).squeeze(0),
        torch.tensor(u8.astype(np.int64)))
    with torch.no_grad():
        o1 = model.model.conv1(xq)
        p1 = model.model.pool1(o1)
        o2 = model.model.conv2(p1)
        p2 = model.model.pool2(o2)
        o3 = model.model.conv3(p2)
        p3 = model.model.pool3(o3)
        o4 = model.model.conv4(p3)
        p4 = model.model.pool4(o4)
        g = torch.flatten(model.model.gap(p4), 1)
        f1 = model.model.fc1(g)
        f2 = model.model.fc2(f1)
        logits = model.dequant(f2)
        probs = torch.softmax(logits, dim=1)
    lg = logits.cpu().numpy()[0]
    pr = probs.cpu().numpy()[0]
    return {"logits": lg, "probs": pr, "top1": int(np.argmax(lg))}


def infer_8f(model, z: np.ndarray) -> dict:
    import torch

    with torch.no_grad():
        logits = model(torch.tensor(z[None, None])).numpy()[0]
    return {"logits": logits, "top1": int(np.argmax(logits))}


def infer_g5(model, z: np.ndarray) -> dict:
    """group5 activity head fed with the last 130 frames (1.5 s contract,
    keep-tail semantics of features.py)."""
    import torch

    z130 = z[:, -130:]
    with torch.no_grad():
        logits = model(torch.tensor(z130[None, None])).numpy()[0]
    return {"logits": logits, "activity": 1.0 / (1.0 + np.exp(-logits))}


# ---------------------------------------------------------------------------
# Per-input comparison.
# ---------------------------------------------------------------------------
def diff_block(z: np.ndarray, z0: np.ndarray) -> dict:
    d = (z.astype(np.float64) - z0.astype(np.float64))
    return {
        "mean": float(d.mean()),
        "abs_mean": float(np.abs(d).mean()),
        "abs_max": float(np.abs(d).max()),
        "std": float(d.std()),
        "l2": float(np.linalg.norm(d)),
        "pearson_r": safe_pearson(z, z0),
    }


def logits_diff_block(cur: dict, base: dict) -> dict:
    d = cur["logits"] - base["logits"]
    blk = {
        "per_element": [float(x) for x in d],
        "abs_max": float(np.abs(d).max()),
        "l2": float(np.linalg.norm(d)),
    }
    if "top1" in cur and "top1" in base:
        blk["top1"] = cur["top1"]
        blk["top1_base"] = base["top1"]
        blk["top1_flip"] = bool(cur["top1"] != base["top1"])
    if "probs" in cur:
        dp = cur["probs"] - base["probs"]
        blk["probs_abs_max"] = float(np.abs(dp).max())
        blk["probs"] = [float(x) for x in cur["probs"]]
    if "activity" in cur:
        da = cur["activity"] - base["activity"]
        blk["activity_abs_max"] = float(np.abs(da).max())
        blk["activity"] = [float(x) for x in cur["activity"]]
    return blk


def run_one_input(inp: dict, quant: dict, models: dict) -> dict:
    s_in = float(quant["s_in"])
    zp_in = int(quant["zp_in"])

    rec = {
        "name": inp["name"],
        "kind": inp["kind"],
        "detail": inp["detail"],
        "pcm48_sha256": sha256_array(inp["pcm48"]),
        "pcm48_samples": int(inp["pcm48"].shape[0]),
        "variants": {},
    }

    feats = {}
    u8s = {}
    infer = {}
    for variant in fv.VARIANTS:
        out = fv.run_frontend(inp["pcm48"], variant)
        feats[variant] = out
        u8s[variant] = fv.quantize_uint8(out["z"], s_in, zp_in)

        vrec = {
            "frames_raw": out["frames_raw"],
            "frame_action": out["frame_action"],
            "z_shape": list(out["z"].shape),
            "z_sha256": sha256_array(out["z"]),
            "z_min": float(out["z"].min()),
            "z_max": float(out["z"].max()),
            "z_mean": float(out["z"].mean()),
            "z_std": float(out["z"].std()),
            "mel_db_min": float(out["mel_db"].min()),
            "mel_db_max": float(out["mel_db"].max()),
            "u8_sha256": sha256_array(u8s[variant]),
        }

        if models.get("8q") is not None:
            infer[(variant, "8q")] = infer_8q(models["8q"], u8s[variant],
                                              s_in, zp_in)
        if models.get("8f") is not None:
            infer[(variant, "8f")] = infer_8f(models["8f"], out["z"])
        if models.get("g5") is not None:
            infer[(variant, "g5")] = infer_g5(models["g5"], out["z"])
        rec["variants"][variant] = vrec

    # Feature / logits drift vs F0.
    for variant in fv.VARIANTS:
        if variant == "F0":
            continue
        rec["variants"][variant]["z_diff_vs_f0"] = diff_block(
            feats[variant]["z"], feats["F0"]["z"])
        for tag in ("8q", "8f", "g5"):
            if (variant, tag) in infer and ("F0", tag) in infer:
                rec["variants"][variant][f"{tag}_diff_vs_f0"] = \
                    logits_diff_block(infer[(variant, tag)],
                                      infer[("F0", tag)])

    # Baseline model outputs (recorded once per input for reference).
    for tag in ("8q", "8f", "g5"):
        if ("F0", tag) in infer:
            base = infer[("F0", tag)]
            blk = {"logits": [float(x) for x in base["logits"]]}
            if "top1" in base:
                blk["top1"] = base["top1"]
                blk["top1_class"] = CLASS_NAMES[base["top1"]]
            if "probs" in base:
                blk["probs"] = [float(x) for x in base["probs"]]
            if "activity" in base:
                blk["activity"] = [float(x) for x in base["activity"]]
            rec["variants"]["F0"][f"{tag}_baseline"] = blk

    return rec


# ---------------------------------------------------------------------------
# Aggregation and report.
# ---------------------------------------------------------------------------
def aggregate(results: list) -> dict:
    agg = {}
    for variant in fv.VARIANTS:
        if variant == "F0":
            continue
        rows = [r["variants"][variant] for r in results]
        pearsons = [row["z_diff_vs_f0"]["pearson_r"]
                    for row in rows if row["z_diff_vs_f0"]["pearson_r"] is not None]
        blk = {
            "n_inputs": len(rows),
            "z_abs_diff_mean_of_max": float(np.mean(
                [row["z_diff_vs_f0"]["abs_max"] for row in rows])),
            "z_abs_diff_mean_of_mean": float(np.mean(
                [row["z_diff_vs_f0"]["abs_mean"] for row in rows])),
            "z_pearson_r_mean": float(np.mean(pearsons)) if pearsons else None,
        }
        for tag in ("8q", "8f"):
            key = f"{tag}_diff_vs_f0"
            vals = [row[key]["abs_max"] for row in rows if key in row]
            flips = [row[key]["top1_flip"] for row in rows if key in row]
            if vals:
                blk[f"{tag}_logit_abs_max_mean"] = float(np.mean(vals))
                blk[f"{tag}_logit_abs_max_overall"] = float(np.max(vals))
                blk[f"{tag}_top1_flips"] = int(sum(flips))
        gkey = "g5_diff_vs_f0"
        gvals = [row[gkey]["activity_abs_max"] for row in rows if gkey in row]
        if gvals:
            blk["g5_activity_abs_max_mean"] = float(np.mean(gvals))
            blk["g5_activity_abs_max_overall"] = float(np.max(gvals))
        agg[variant] = blk
    return agg


def build_conclusions(agg: dict, sanity: dict, models: dict) -> list:
    import torch
    cons = []

    def fm(x):
        return "%.3f" % x

    if "F1" in agg:
        cons.append(
            "F1 (native 48k, resampler removed) deviates from F0 by "
            "mean|dz|=%s / max|dz|=%s (z units), Pearson r=%s: the "
            "per-bin feature is NOT interchangeable with the F0 feature."
            % (fm(agg["F1"]["z_abs_diff_mean_of_mean"]),
               fm(agg["F1"]["z_abs_diff_mean_of_max"]),
               fm(agg["F1"]["z_pearson_r_mean"] or 0.0)))
    if "F2" in agg:
        cons.append(
            "F2 (24k decimated) deviates from F0 by mean|dz|=%s / "
            "max|dz|=%s, Pearson r=%s; both the Mel remap (fmax 22050 -> "
            "12000) and the 0.94 ms hop time-base shift contribute."
            % (fm(agg["F2"]["z_abs_diff_mean_of_mean"]),
               fm(agg["F2"]["z_abs_diff_mean_of_max"]),
               fm(agg["F2"]["z_pearson_r_mean"] or 0.0)))
    if "F2b" in agg:
        cons.append(
            "F2b (16k) is a pipeline-only control route: mean|dz|=%s, "
            "fmax collapses to 8 kHz so the upper ~21 Mel channels lose "
            "nearly all spectral energy; accuracy numbers are reference "
            "only." % fm(agg["F2b"]["z_abs_diff_mean_of_mean"]))

    for tag, label in (("8q", "deployed quantized 8-class"),
                       ("8f", "float 8-class")):
        if agg.get("F1", {}).get(f"{tag}_logit_abs_max_mean") is not None:
            cons.append(
                "Feeding the %s model with F1/F2/F2b features shifts the "
                "logits by up to %s / %s / %s (mean of per-input max, "
                "F1/F2/F2b) and flips the top-1 class on %d/%d/%d of %d "
                "inputs -> old weights cannot be reused without retraining."
                % (label,
                   fm(agg["F1"].get(f"{tag}_logit_abs_max_mean", 0.0)),
                   fm(agg["F2"].get(f"{tag}_logit_abs_max_mean", 0.0)),
                   fm(agg["F2b"].get(f"{tag}_logit_abs_max_mean", 0.0)),
                   agg["F1"].get(f"{tag}_top1_flips", 0),
                   agg["F2"].get(f"{tag}_top1_flips", 0),
                   agg["F2b"].get(f"{tag}_top1_flips", 0),
                   agg["F1"]["n_inputs"]))

    if models.get("g5") is not None:
        cons.append(
            "The group5 v3 float model shows activity drift up to %s / "
            "%s / %s (F1/F2/F2b max over inputs), same retraining "
            "requirement for the 5-group head."
            % (fm(agg["F1"].get("g5_activity_abs_max_overall", 0.0)),
               fm(agg["F2"].get("g5_activity_abs_max_overall", 0.0)),
               fm(agg["F2b"].get("g5_activity_abs_max_overall", 0.0))))

    if sanity["all_pass"]:
        cons.append(
            "All sanity checks passed (S1 Mel table, S2 features.py "
            "parity, S3 quantization parity), so the drift numbers above "
            "are measured on a chain that reproduces the production F0 "
            "contract (librosa %s / torch %s)."
            % (importlib.import_module("librosa").__version__, torch.__version__))
    else:
        cons.append("WARNING: sanity checks did NOT all pass; drift "
                    "numbers may include implementation error.")
    return cons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wav", action="append", default=[],
                        help="extra WAV input(s), repeated allowed")
    parser.add_argument("--out", default=str(DEFAULT_REPORT),
                        help="output JSON report path")
    args = parser.parse_args()

    import librosa
    import scipy
    import torch

    print("== audio_frontend comparison run ==")
    print("python %s, numpy %s, torch %s, librosa %s, scipy %s"
          % (sys.version.split()[0], np.__version__, torch.__version__,
             librosa.__version__, scipy.__version__))

    # Assets.
    assets = []
    for path, role in ASSET_FILES:
        if path.exists():
            assets.append({
                "path": str(path.relative_to(PROJ)) if PROJ in path.parents
                        or path.parent == PROJ else str(path),
                "sha256": sha256_file(path),
                "role": role,
                "available": True,
            })
        else:
            assets.append({"path": str(path), "sha256": None,
                           "role": role, "available": False})
    for wav in FIXTURE_WAVS + REAL_WAVS:
        assets.append({
            "path": str(wav.relative_to(PROJ)) if PROJ in wav.parents
                    or wav.parent == PROJ else str(wav),
            "sha256": sha256_file(wav),
            "role": "input signal",
            "available": True,
        })
    print("assets hashed: %d" % len(assets))

    # Quantization contract.
    with open(PROJ / "scripts" / "outputs" / "layer_contract.json",
              "r", encoding="utf-8") as fh:
        contract = json.load(fh)
    quant = contract["quant_stub_input_contract"]

    # Sanity checks.
    sanity = run_sanity_checks(quant)
    print("sanity: S1 %s | S2 %s | S3 %s"
          % ("PASS" if sanity["S1_mel_table_match"]["pass"] else "FAIL",
             "PASS" if sanity["S2_features_py_match"]["pass"] else "FAIL",
             "PASS" if sanity["S3_quantize_match"]["pass"] else "FAIL"))

    # Models.
    models = load_models()
    for tag in ("8q", "8f", "g5"):
        status = "ok" if models.get(tag) is not None else \
            "UNAVAILABLE (%s)" % models.get(tag + "_error", "?")
        print("model %s: %s" % (tag, status))

    # Inputs.
    inputs = synth_inputs() + wav_inputs(args.wav)
    print("inputs: %d (%d synthetic, %d fixture, %d real, %d user)"
          % (len(inputs), 3, len(FIXTURE_WAVS), len(REAL_WAVS),
             len(args.wav)))

    # Main loop.
    results = []
    for inp in inputs:
        rec = run_one_input(inp, quant, models)
        results.append(rec)
        f0 = rec["variants"]["F0"]
        line = ["%-26s" % inp["name"]]
        for variant in fv.VARIANTS:
            v = rec["variants"][variant]
            d = v.get("z_diff_vs_f0")
            if d is None:
                line.append("%s z[%.1f..%.1f]" % (variant, f0["z_min"],
                                                  f0["z_max"]))
            else:
                line.append("%s |dz|max=%.2f" % (variant, d["abs_max"]))
        print(" ".join(line))

    # Aggregate.
    agg = aggregate(results)

    # FIR / config tables for the report.
    fir_stats = {v: fv.fir_response_stats(v) for v in ("F2", "F2b")}
    for k, st in fir_stats.items():
        print("FIR %s: %d taps, stopband %.1f dB"
              % (k, st["taps"], st["stopband_attenuation_db"]))

    conclusions = build_conclusions(agg, sanity, models)

    report = {
        "report": "audio_frontend_comparison_20261104",
        "purpose": "dual-mode (8-class + 5-group activity) front-end route "
                   "study: F0 baseline vs F1 native-48k vs F2 decimated-24k "
                   "vs F2b decimated-16k, float-domain numeric comparison "
                   "infrastructure",
        "determinism": {
            "seed": SEED,
            "note": "no wall-clock timestamps; repeated runs are "
                    "byte-identical (fixed tables, fixed FIR taps, "
                    "seeded synthesis, torch single-thread eval)",
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "torch": torch.__version__,
            "librosa": librosa.__version__,
            "scipy": scipy.__version__,
            "torch_threads": 1,
        },
        "input_contract": {
            "front_end_sr_hz": fv.INPUT_SR,
            "window_seconds": INPUT_SECONDS,
            "note": "every input is normalized to the 48 kHz float domain "
                    "(physical PCM1808 input) so all four variants consume "
                    "the identical PCM; fixtures/demo WAVs are mono-mixed "
                    "and up-sampled 44.1k -> 48k with soxr_hq",
        },
        "quant_stub_input_contract": quant,
        "assets": assets,
        "data_gaps": [
            "No Medley-solos-DB validation audio on this machine; the "
            "real clips are 8 IRMAS demo slices (one per instrument, "
            "3 s each), not a validation set",
            "No 'female singer' and no 'distorted electric guitar' demo "
            "clip exists in InstRec/data/demo/irmas_test (guitar_electric "
            "is the closest neighbour, guitar_acoustic is out of class)",
            "The 8-class accuracy effect of F1/F2 therefore cannot be "
            "concluded from this run; only the numeric drift of features "
            "and logits on synthetic + demo inputs is measured",
        ],
        "sanity_checks": sanity,
        "frontend_configs": fv.FRONTEND_CONFIGS,
        "fir_designs": fir_stats,
        "models": {
            "8q": {
                "path": str(INSTREC / "deploy" / "quantized_model.pt"),
                "available": models.get("8q") is not None,
                "input": "uint8 (64, 258) via layer_contract quant stub",
            },
            "8f": {
                "path": str(INSTREC / "runs" / "best_model.pt"),
                "available": models.get("8f") is not None,
                "input": "float32 (1, 1, 64, 258)",
            },
            "g5": {
                "path": str(PROJ / "models" / "group5_v3_float_20261102"),
                "available": models.get("g5") is not None,
                "input": "float32 (1, 1, 64, 130) keep-tail 1.5 s contract",
            },
        },
        "class_names": CLASS_NAMES,
        "group_names": GROUP_NAMES,
        "inputs": [
            {"name": r["name"], "kind": r["kind"], "detail": r["detail"],
             "pcm48_sha256": r["pcm48_sha256"],
             "pcm48_samples": r["pcm48_samples"]}
            for r in results
        ],
        "results": results,
        "summary": agg,
        "conclusions": conclusions,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("report written: %s (%d bytes)"
          % (out_path, out_path.stat().st_size))

    # Console summary.
    print("\n== summary (mean over %d inputs) ==" % len(results))
    header = "%-6s %-12s %-12s %-10s %-14s %-8s" % (
        "var", "|dz| mean", "|dz| max", "pearson", "|dlogits| 8q", "flips")
    print(header)
    for variant in fv.VARIANTS:
        if variant == "F0":
            print("%-6s baseline" % variant)
            continue
        a = agg[variant]
        print("%-6s %-12s %-12s %-10s %-14s %-8s" % (
            variant,
            "%.3f" % a["z_abs_diff_mean_of_mean"],
            "%.3f" % a["z_abs_diff_mean_of_max"],
            "%.4f" % (a["z_pearson_r_mean"] or float("nan")),
            "%.3f" % a.get("8q_logit_abs_max_mean", float("nan")),
            "%d" % a.get("8q_top1_flips", -1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
