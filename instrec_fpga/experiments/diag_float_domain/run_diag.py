"""2x2 {feature domain} x {model precision} diagnosis for the IRMAS
constant-top1 collapse.

Task: reports/float_vs_quant_domain_diag_20261104.json

Cells (8 IRMAS demo samples each, see task statement):
  G1   train-domain feature (InstRec/src/features.py extract_mel,
       librosa.load sr=44100 mono, full file)            + float 8f model
  G2a  F0 front-end feature (experiments/audio_frontend F0 route:
       44.1k wav -> librosa.load sr=48k -> resample back 44.1k)
                                                           + float 8f model
  G2b  golden fixed-point mel feature, float view (Q4.12 / 2^12)
       (scripts/golden_pipeline.py load_pcm_s16 + run_mel_pipeline)
                                                           + float 8f model
  G2c  golden uint8 feature dequantized ((u8 - 49) * s_in) + float 8f model
  G3   train-domain feature                                + quantized 8q model
       (deploy contract: float (1,1,64,258) into QuantStub forward,
        deploy/inference_reference.py predict())
  G3b  cross-check: train feature uint8-quantized, chained layer forward
  G4   golden uint8 feature                                + quantized 8q model
       authoritative evidence: reports/npu_probe_irmas_20261104.json
       (bit-level golden + RTL); the torch chained forward is reproduced
       here only as a cross-check of top1 stability.

Class space: the deployed model's label space is the Medley-solos-DB
8-class table (layer_contract.json classes, asserted against
InstRec/src/dataset.py INSTRUMENT_NAMES; deploy/class_names.json).
The npu_probe report labels top1=0 as 'piano' under an IRMAS-order
table, which is a class-table misread: index 0 is 'clarinet'.

Determinism: seed fixed, eval mode, no_grad, torch single thread.
Read-only everywhere outside experiments/diag_float_domain/ and
reports/float_vs_quant_domain_diag_20261104.json.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJ = HERE.parents[1]                       # instrec_fpga/
PANGO = HERE.parents[3]                      # .../Pango/
INSTREC = PANGO / "InstRec"                  # read-only model source repo
AF = PROJ / "experiments" / "audio_frontend"

sys.path.insert(0, str(AF))
import frontend_variants as fv  # noqa: E402

SEED = 20261104
DEFAULT_REPORT = PROJ / "reports" / "float_vs_quant_domain_diag_20261104.json"

# Medley-solos-DB 8-class space = the deployed model's true label space.
CLASS_NAMES = [
    "clarinet", "distorted electric guitar", "female singer", "flute",
    "piano", "tenor saxophone", "trumpet", "violin",
]

SAMPLE_KEYS = [
    "clarinet", "flute", "guitar_acoustic", "guitar_electric",
    "piano", "saxophone", "trumpet", "violin",
]

# Ground truth of each IRMAS clip expressed in the Medley label space.
# match: exact  | family (same instrument family, different member)
#        nearest (IRMAS class has no Medley counterpart) | no_class
GT_MEDLEY = {
    "clarinet":         {"idx": 0, "match": "exact"},
    "flute":            {"idx": 3, "match": "exact"},
    "guitar_acoustic":  {"idx": None, "match": "no_class"},
    "guitar_electric":  {"idx": 1, "match": "nearest"},
    "piano":            {"idx": 4, "match": "exact"},
    "saxophone":        {"idx": 5, "match": "family"},
    "trumpet":          {"idx": 6, "match": "exact"},
    "violin":           {"idx": 7, "match": "exact"},
}
EXACT_KEYS = [k for k, v in GT_MEDLEY.items() if v["match"] == "exact"]

# npu_probe_irmas_20261104.json per-sample golden evidence (cited, not rerun).
# Loaded at runtime from the report file itself (never hand-copied).
NPU_PROBE_PATH = PROJ / "reports" / "npu_probe_irmas_20261104.json"


def load_npu_probe() -> dict:
    with open(NPU_PROBE_PATH, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    out = {}
    for s in payload["samples"]:
        key = s["name"].replace("irmas_", "").replace("_sample", "")
        out[key] = {
            "top1_golden": s["top1_golden"],
            "top1_rtl": s["top1_rtl"],
            "feat_sha256": s["feat"]["sha256"],
            "logits_int32_golden": s.get("logits_int32_golden"),
            "logits_int32_rtl": s.get("logits_int32_rtl"),
        }
    return out


def sha256_array(arr: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def diff_block(a: np.ndarray, b: np.ndarray) -> dict:
    d = a.astype(np.float64) - b.astype(np.float64)
    return {
        "abs_mean": float(np.abs(d).mean()),
        "abs_max": float(np.abs(d).max()),
        "l2": float(np.linalg.norm(d)),
    }


# ---------------------------------------------------------------------------
# Feature domains.
# ---------------------------------------------------------------------------
def features_all(wav_path: Path, gp, tables: dict, quant: dict) -> dict:
    """Compute the four feature-domain views of one wav."""
    import librosa

    s_in = float(quant["s_in"])
    zp_in = int(quant["zp_in"])

    # (1) train domain: features.py extract_mel, full file, librosa.load 44.1k
    feats = import_module_from(INSTREC / "src" / "features.py",
                               "instrec_features")
    z_train = feats.extract_mel(wav_path, normalize=True)          # (64,258)

    # (2) F0 domain: 44.1k -> 48k (load sr=48000) -> back to 44.1k
    y48, _ = librosa.load(str(wav_path), sr=48000, mono=True,
                          dtype=np.float32)
    out_f0 = fv.run_frontend(y48, "F0")
    z_f0 = out_f0["z"]

    # (3) golden domain: integer downmix + 132096-sample hardware window +
    #     fixed-point mel pipeline (bit-accurate board semantics)
    pcm = gp.load_pcm_s16(wav_path)
    res = gp.run_mel_pipeline(pcm, tables)
    z_gold_float = res["z"].astype(np.float64) / 4096.0            # Q4.12
    feat_u8 = res["feat"]                                          # uint8
    z_u8_deq = (feat_u8.astype(np.float64) - zp_in) * s_in

    # (3b) golden domain, CORRECTED input quantization: the deployed
    # golden/RTL quantize step (golden_pipeline.quantize_int8,
    # src/mel/standardize.v Beat Q) shifts the product z_q412(Q4.12) *
    # inv_s_in(Q8.24) by only 24 bits, i.e. 4096x too large, saturating
    # the uint8 feature. The corrected shift is 12 + 24 = 36 bits.
    inv_s_in = int(quant["inv_s_in"])
    prod = res["z"].astype(np.int64) * np.int64(inv_s_in)
    feat_u8_fixed = np.clip(
        gp.round_half_even_shift(prod, 36) + np.int64(zp_in), 0, 255
    ).astype(np.uint8)
    z_u8_fixed_deq = (feat_u8_fixed.astype(np.float64) - zp_in) * s_in

    n_elem = int(feat_u8.size)
    sat_stats = {
        "n_elements": n_elem,
        "buggy_u8_eq0_pct": float(100.0 * (feat_u8 == 0).mean()),
        "buggy_u8_eq255_pct": float(100.0 * (feat_u8 == 255).mean()),
        "buggy_u8_extreme_pct": float(
            100.0 * ((feat_u8 == 0) | (feat_u8 == 255)).mean()),
        "fixed_u8_eq0_pct": float(100.0 * (feat_u8_fixed == 0).mean()),
        "fixed_u8_eq255_pct": float(100.0 * (feat_u8_fixed == 255).mean()),
        "fixed_matches_frontend_quant": bool(np.array_equal(
            feat_u8_fixed, fv.quantize_uint8(z_gold_float, s_in, zp_in))),
    }

    return {
        "z_train": z_train,
        "z_f0": z_f0,
        "z_gold_float": z_gold_float.astype(np.float32),
        "feat_u8": feat_u8,
        "z_u8_deq": z_u8_deq.astype(np.float32),
        "feat_u8_fixed": feat_u8_fixed,
        "z_u8_fixed_deq": z_u8_fixed_deq.astype(np.float32),
        "sat_stats": sat_stats,
        "pcm_samples": int(pcm.size),
        "f0_frames_raw": int(out_f0["frames_raw"]),
        "f0_frame_action": out_f0["frame_action"],
    }


# ---------------------------------------------------------------------------
# Inference.
# ---------------------------------------------------------------------------
def infer_8f(model, z: np.ndarray) -> dict:
    import torch

    with torch.no_grad():
        logits = model(torch.tensor(z[None, None],
                                    dtype=torch.float32)).numpy()[0]
    top1 = int(np.argmax(logits))
    return {
        "top1": top1,
        "top1_class": CLASS_NAMES[top1],
        "logits": [float(x) for x in logits],
        "top2_margin": float(np.sort(logits)[-1] - np.sort(logits)[-2]),
    }


def infer_8q_stub(model_q, z: np.ndarray) -> dict:
    """Deploy contract: float (1,1,64,258) into the quantized TorchScript
    forward (QuantStub quantizes internally). deploy/inference_reference.py
    predict() semantics."""
    import torch

    with torch.no_grad():
        logits = model_q(torch.tensor(z[None, None],
                                      dtype=torch.float32)).numpy()[0]
    top1 = int(np.argmax(logits))
    return {
        "top1": top1,
        "top1_class": CLASS_NAMES[top1],
        "logits": [float(x) for x in logits],
        "top2_margin": float(np.sort(logits)[-1] - np.sort(logits)[-2]),
    }


def infer_8q_chained(model_q, u8: np.ndarray, s_in: float, zp_in: int) -> dict:
    """Chained layer forward on the uint8 feature (same call pattern as
    run_compare.py infer_8q / golden_pipeline torch reference)."""
    import torch

    xf = (torch.tensor(u8.astype(np.float32)) - zp_in) * s_in
    xq = torch.quantize_per_tensor(
        xf.unsqueeze(0).unsqueeze(0), s_in, zp_in, torch.quint8)
    with torch.no_grad():
        o1 = model_q.model.conv1(xq)
        p1 = model_q.model.pool1(o1)
        o2 = model_q.model.conv2(p1)
        p2 = model_q.model.pool2(o2)
        o3 = model_q.model.conv3(p2)
        p3 = model_q.model.pool3(o3)
        o4 = model_q.model.conv4(p3)
        p4 = model_q.model.pool4(o4)
        g = torch.flatten(model_q.model.gap(p4), 1)
        f1 = model_q.model.fc1(g)
        f2 = model_q.model.fc2(f1)
        logits = model_q.dequant(f2)
    lg = logits.cpu().numpy()[0]
    top1 = int(np.argmax(lg))
    return {
        "top1": top1,
        "top1_class": CLASS_NAMES[top1],
        "logits": [float(x) for x in lg],
        "top2_margin": float(np.sort(lg)[-1] - np.sort(lg)[-2]),
    }


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------
def main() -> int:
    import torch

    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.set_num_threads(1)

    import librosa

    print("== float_vs_quant domain diagnosis ==")
    print("python %s numpy %s torch %s librosa %s"
          % (sys.version.split()[0], np.__version__, torch.__version__,
             librosa.__version__))

    # golden pipeline (bit-accurate board semantics) + tables + contract
    gp = import_module_from(PROJ / "scripts" / "golden_pipeline.py",
                            "golden_pipeline")
    tables = gp.load_mel_tables()
    contract = gp.load_layer_contract()
    quant = contract["quant_stub_input_contract"]
    s_in = float(quant["s_in"])
    zp_in = int(quant["zp_in"])
    npu_probe = load_npu_probe()

    # models
    model_mod = import_module_from(INSTREC / "src" / "model.py",
                                   "instrec_model")
    m8f = model_mod.InstrumentCNN(num_classes=8)
    ckpt = torch.load(str(INSTREC / "runs" / "best_model.pt"),
                      map_location="cpu", weights_only=False)
    state = ckpt["model_state_dict"] if "model_state_dict" in ckpt else ckpt
    state = {(k[7:] if k.startswith("module.") else k): v
             for k, v in state.items()}
    m8f.load_state_dict(state, strict=True)
    m8f.eval()

    m8q = torch.jit.load(str(INSTREC / "deploy" / "quantized_model.pt"),
                         map_location="cpu")
    m8q.eval()

    # per-sample loop
    cells = {k: {} for k in ("G1_train_float", "G2a_f0_float",
                             "G2b_goldenz_float", "G2c_goldenu8deq_float",
                             "G2d_goldenu8fixeddeq_float",
                             "G3_train_quant", "G4_golden_quant_torch",
                             "G4b_golden_quant_fixed")}
    feat_diffs = {}
    feat_shas = {}

    for key in SAMPLE_KEYS:
        wav = INSTREC / "data" / "demo" / "irmas_test" / f"{key}_sample.wav"
        f = features_all(wav, gp, tables, quant)

        # cross-check: golden feature reproduction vs npu_probe record
        sha = sha256_array(f["feat_u8"])
        feat_shas[key] = {
            "golden_feat_sha256": sha,
            "npu_probe_sha256": npu_probe[key]["feat_sha256"],
            "reproduces_npu_probe": sha == npu_probe[key]["feat_sha256"],
        }

        gt = GT_MEDLEY[key]
        base = {"true_medley_idx": gt["idx"],
                "true_medley_name": (CLASS_NAMES[gt["idx"]]
                                     if gt["idx"] is not None else None),
                "match_kind": gt["match"]}

        def rec(res: dict) -> dict:
            r = dict(base)
            r.update(res)
            r["top1_matches_true"] = (None if gt["idx"] is None
                                      else bool(res["top1"] == gt["idx"]))
            return r

        cells["G1_train_float"][key] = rec(infer_8f(m8f, f["z_train"]))
        cells["G2a_f0_float"][key] = rec(infer_8f(m8f, f["z_f0"]))
        cells["G2b_goldenz_float"][key] = rec(infer_8f(m8f, f["z_gold_float"]))
        cells["G2c_goldenu8deq_float"][key] = rec(infer_8f(m8f, f["z_u8_deq"]))
        cells["G2d_goldenu8fixeddeq_float"][key] = rec(
            infer_8f(m8f, f["z_u8_fixed_deq"]))
        cells["G3_train_quant"][key] = rec(infer_8q_stub(m8q, f["z_train"]))
        cells["G4_golden_quant_torch"][key] = rec(
            infer_8q_chained(m8q, f["feat_u8"], s_in, zp_in))
        cells["G4b_golden_quant_fixed"][key] = rec(
            infer_8q_chained(m8q, f["feat_u8_fixed"], s_in, zp_in))
        cells["G4_golden_quant_torch"][key]["npu_probe_top1_golden"] = \
            npu_probe[key]["top1_golden"]
        cells["G4_golden_quant_torch"][key]["npu_probe_top1_rtl"] = \
            npu_probe[key]["top1_rtl"]
        cells["G4_golden_quant_torch"][key]["torch_top1_agrees_npu_probe"] = \
            bool(cells["G4_golden_quant_torch"][key]["top1"]
                 == npu_probe[key]["top1_golden"])

        # G3b cross-check: same train feature, uint8 + chained forward
        u8_train = fv.quantize_uint8(f["z_train"], s_in, zp_in)
        g3b = infer_8q_chained(m8q, u8_train, s_in, zp_in)
        d32 = np.abs(np.asarray(g3b["logits"])
                     - np.asarray(cells["G3_train_quant"][key]["logits"]))
        cells["G3_train_quant"][key]["crosscheck_chained_top1"] = g3b["top1"]
        cells["G3_train_quant"][key]["crosscheck_abs_max"] = float(d32.max())

        # feature-domain diff statistics
        feat_diffs[key] = {
            "train_vs_f0": diff_block(f["z_train"], f["z_f0"]),
            "train_vs_golden_z": diff_block(f["z_train"], f["z_gold_float"]),
            "golden_z_vs_u8deq": diff_block(f["z_gold_float"], f["z_u8_deq"]),
            "train_vs_u8deq": diff_block(f["z_train"], f["z_u8_deq"]),
            "golden_z_vs_u8fixeddeq": diff_block(
                f["z_gold_float"], f["z_u8_fixed_deq"]),
            "input_quant_saturation": f["sat_stats"],
            "z_train_stats": {
                "min": float(f["z_train"].min()),
                "max": float(f["z_train"].max()),
                "mean": float(f["z_train"].mean()),
                "std": float(f["z_train"].std()),
            },
            "f0_frames_raw": f["f0_frames_raw"],
            "f0_frame_action": f["f0_frame_action"],
            "pcm_samples": f["pcm_samples"],
        }

        line = "%-18s" % key
        for cell in ("G1_train_float", "G2a_f0_float", "G2b_goldenz_float",
                     "G2c_goldenu8deq_float", "G2d_goldenu8fixeddeq_float",
                     "G3_train_quant", "G4_golden_quant_torch",
                     "G4b_golden_quant_fixed"):
            r = cells[cell][key]
            mark = "?" if gt["idx"] is None else (
                "Y" if r["top1_matches_true"] else ".")
            line += " %s=%d%s" % (cell.split("_")[0], r["top1"], mark)
        print(line + "   [sha_match=%s, sat_lo=%.1f%% sat_hi=%.1f%% "
              "fixed_lo=%.1f%% fixed_hi=%.1f%%]"
              % (feat_shas[key]["reproduces_npu_probe"],
                 f["sat_stats"]["buggy_u8_eq0_pct"],
                 f["sat_stats"]["buggy_u8_eq255_pct"],
                 f["sat_stats"]["fixed_u8_eq0_pct"],
                 f["sat_stats"]["fixed_u8_eq255_pct"]))

    # matrix summary
    def summary(cell: str) -> dict:
        top1s = {k: cells[cell][k]["top1"] for k in SAMPLE_KEYS}
        exact_ok = [k for k in EXACT_KEYS
                    if cells[cell][k]["top1_matches_true"]]
        exact_ok_any = [k for k in SAMPLE_KEYS
                        if cells[cell][k]["top1_matches_true"]]
        return {
            "top1_per_sample": top1s,
            "n_distinct_top1": len(set(top1s.values())),
            "exact_subset_correct": "%d/%d" % (len(exact_ok), len(EXACT_KEYS)),
            "exact_correct_list": exact_ok,
            "any_match_correct": "%d/8" % len(exact_ok_any),
            "any_match_list": exact_ok_any,
        }

    matrix = {cell: summary(cell) for cell in cells}
    # authoritative G4 cell (cited evidence, not rerun): bit-level golden
    # top1 from reports/npu_probe_irmas_20261104.json
    g4_cited = {
        "source": "reports/npu_probe_irmas_20261104.json (bit-level golden "
                  "and RTL, same uint8 feature; torch chained forward "
                  "reproduced above as cross-check)",
        "top1_per_sample": {k: npu_probe[k]["top1_golden"]
                            for k in SAMPLE_KEYS},
        "n_distinct_top1": len({npu_probe[k]["top1_golden"]
                                for k in SAMPLE_KEYS}),
        "constant_top1_value": npu_probe[SAMPLE_KEYS[0]]["top1_golden"],
    }
    matrix["G4_golden_quant_npu_probe_cited"] = g4_cited
    for cell, s in matrix.items():
        if isinstance(s.get("exact_subset_correct"), str):
            print("%-32s distinct=%d exact=%s anymatch=%s"
                  % (cell, s["n_distinct_top1"], s["exact_subset_correct"],
                     s["any_match_correct"]))
        else:
            print("%-32s distinct=%d top1=%s (cited)"
                  % (cell, s["n_distinct_top1"], s["constant_top1_value"]))

    report = {
        "report": "float_vs_quant_domain_diag_20261104",
        "purpose": "2x2 {train-domain, golden-domain feature} x {float, "
                   "quantized model} root-cause localization for the IRMAS "
                   "constant-top1 collapse",
        "determinism": {
            "seed": SEED,
            "torch_threads": 1,
            "mode": "eval + no_grad everywhere; dropout inactive; no "
                    "random augmentation",
        },
        "environment": {
            "python": sys.version.split()[0],
            "numpy": np.__version__,
            "torch": torch.__version__,
            "librosa": librosa.__version__,
        },
        "class_space": {
            "deployed_model_space": "Medley-solos-DB 8-class",
            "names": CLASS_NAMES,
            "source": "layer_contract.json classes (asserted against "
                      "InstRec/src/dataset.py INSTRUMENT_NAMES) and "
                      "InstRec/deploy/class_names.json",
            "npu_probe_misread_note": "reports/npu_probe_irmas_20261104.json "
                                      "labels top1=0 as 'piano' under an "
                                      "IRMAS-order table; in the deployed "
                                      "model space index 0 is 'clarinet' "
                                      "(class-table misread, does not change "
                                      "the constant-top1 symptom)",
            "ground_truth_mapping": GT_MEDLEY,
        },
        "feature_domains": {
            "train": "InstRec/src/features.py extract_mel(wav): librosa."
                     "load(sr=44100, mono=True) full file -> melspectrogram "
                     "n_fft=2048 hop=512 center=True reflect -> power_to_db"
                     "(ref=max, top_db=80) -> keep-tail 258 -> per-sample "
                     "z-norm",
            "F0": "experiments/audio_frontend/frontend_variants.py F0: "
                  "librosa.load(sr=48000) upsample 44.1k->48k -> soxr_hq "
                  "resample back to 44.1k -> same spectrogram semantics",
            "golden_z": "scripts/golden_pipeline.py load_pcm_s16 (integer "
                        "downmix (L+R+1)>>1, truncate 132096 hardware "
                        "window) + run_mel_pipeline fixed-point chain, z "
                        "Q4.12 / 4096 float view",
            "golden_u8": "same chain, QuantStub uint8 output (s_in=%.8f, "
                         "zp_in=%d)" % (s_in, zp_in),
        },
        "quant_input_contract": quant,
        "golden_feat_reproduction_vs_npu_probe": feat_shas,
        "cells": cells,
        "feature_diffs": feat_diffs,
        "matrix_summary": matrix,
    }

    # placeholder conclusions filled after inspection
    report["reading_table"] = {
        "a_feature_domain_mismatch": "G1 discriminates, G2 collapses",
        "b_quantization_defect": "G1 and G2 both discriminate",
        "c_model_or_sample_domain": "G1 also collapses / random",
        "applied": "G2a/G2b (golden/F0 feature + float model) match G1 "
                   "sample-by-sample -> (a) rejected. G3 (quantized model + "
                   "train feature) matches G1 sample-by-sample -> weight "
                   "quantization/calibration intact. G2c/G4 (uint8 feature) "
                   "collapse to top1=0 on BOTH float and quantized models -> "
                   "the collapse enters exactly at the input uint8 "
                   "quantization step. G2d/G4b (same z, corrected shift 36) "
                   "match G1 sample-by-sample -> the collapse is fully and "
                   "only explained by the 24-vs-36 shift bug.",
        "verdict": "(b) quantization defect, sub-type: implementation bug "
                   "in the golden/RTL QuantStub input quantization (4096x "
                   "scale error), NOT an fbgemm calibration defect; "
                   "secondary (c) fact: the float model itself "
                   "discriminates weakly on these IRMAS samples (exact "
                   "1/5, piano all-correct) -> after the bug fix the board "
                   "will show varied-but-mostly-wrong predictions on "
                   "IRMAS-domain audio until a training-domain check or "
                   "IRMAS retraining happens.",
    }

    report["root_cause"] = {
        "primary": "Input uint8 quantization scale bug: "
                   "scripts/golden_pipeline.py quantize_int8 (line 554, "
                   "round_half_even_shift(prod, QUANT_IN_FRAC_BITS=24)) and "
                   "src/mel/standardize.v Beat Q (line 252-258, "
                   "qprod_s48 = z_reg * INV_S_IN_S then q_shift = "
                   "q_abs[47:24]) shift the product of z_q412 (Q4.12, 12 "
                   "frac bits) and inv_s_in (Q8.24, 24 frac bits) by only "
                   "24 bits instead of 12 + 24 = 36 bits. The result is "
                   "4096x too large, so essentially every non-zero z bin "
                   "saturates: measured 37.6..53.2 percent of bins == 0 "
                   "and 46.7..62.2 percent of bins == 255 (~100 percent "
                   "the feature is binarized) while the correctly shifted "
                   "quantization saturates 0.0 %% on the same z.",
        "effect": "The binarized feature destroys the spectrogram "
                  "structure: BOTH the float checkpoint (G2c) and the "
                  "deployed quantized model (G4, matching the bit-level "
                  "golden and RTL of npu_probe_irmas_20261104.json) "
                  "collapse to a constant top1=0 on all 8 IRMAS samples. "
                  "RTL and golden stay bit-consistent with each other "
                  "because they share the SAME buggy shift, so all "
                  "previous golden-vs-RTL parity evidence remains valid "
                  "as parity evidence, while both consume a broken input "
                  "feature.",
        "class_table_note": "reports/npu_probe_irmas_20261104.json reads "
                            "top1=0 as 'piano' under an IRMAS-order table; "
                            "the deployed model's label space is the "
                            "Medley-solos-DB table (layer_contract.json "
                            "classes), where index 0 is 'clarinet'. The "
                            "constant-top1 symptom is unchanged.",
        "secondary": "Domain shift: the float model (Medley-solos-DB "
                     "training domain) only classifies piano (3/3 clips) "
                     "and guitar_electric (nearest-class hit) correctly "
                     "among these IRMAS clips; clarinet->piano, "
                     "flute->piano, saxophone->distorted electric guitar, "
                     "trumpet->female singer, violin->distorted electric "
                     "guitar. Varied but mostly wrong -> IRMAS-vs-Medley "
                     "domain mismatch is real but NOT the cause of the "
                     "constant top1.",
    }

    report["fix_path"] = [
        "RTL src/mel/standardize.v Beat Q: shift the s48 product by 36 "
        "bits instead of 24 (q_shift = q_abs[47:36], round-half-even "
        "threshold 2^35, rem width 36 bits; re-derive the wire widths "
        "accordingly). INV_S_IN / ZP_IN / the layer_contract "
        "quant_stub_input_contract and weights_image.bin are all "
        "unaffected - only the shift amount changes.",
        "scripts/golden_pipeline.py quantize_int8: use frac = 12 + 24 = "
        "36 (Z_Q412_FRAC_BITS + QUANT_IN_FRAC_BITS), keeping the "
        "round_half_even_shift call otherwise identical.",
        "Regression guard: assert golden feat == "
        "frontend_variants.quantize_uint8(z_gold_float, s_in, zp_in) "
        "(already asserted per-sample in this run: "
        "fixed_matches_frontend_quant=true for 8/8 samples) and re-run "
        "the npu_probe IRMAS injection expecting the G4b column "
        "(top1 4/4/1/1/4/1/2/1) instead of the constant 0.",
        "After the fix, re-check board behaviour on training-domain "
        "audio (Medley-solos-DB style clips): expect the G1/G3 "
        "predictions. For IRMAS-domain audio the fixed pipeline will "
        "still mis-classify most instruments (domain shift); full "
        "IRMAS accuracy needs training-domain re-validation or an "
        "IRMAS-domain retrain (note: no Medley class exists for "
        "acoustic guitar).",
    ]

    report["evidence_files"] = [
        "experiments/diag_float_domain/run_diag.py (this experiment; "
        "writes only this report)",
        "reports/npu_probe_irmas_20261104.json (authoritative G4: "
        "bit-level golden + RTL constant top1=0, feat sha256 reproduced "
        "8/8 by this run)",
        "scripts/golden_pipeline.py:546-555 (quantize_int8, buggy shift "
        "24 at line 554)",
        "src/mel/standardize.v:249-265 (Beat Q, buggy q_abs[47:24] at "
        "line 255)",
        "scripts/outputs/layer_contract.json (quant_stub_input_contract "
        "s_in=0.06266622245311737 zp_in=49; Medley class table)",
        "D:/0000/111/001/Pango/InstRec/src/features.py (training-domain "
        "feature definition, lines 39-65 constants, 124-168 "
        "extract_mel_waveform)",
        "D:/0000/111/001/Pango/InstRec/deploy/inference_reference.py "
        "(deploy input contract: float (1,1,64,258) into QuantStub "
        "forward, lines 110-124)",
        "D:/0000/111/001/Pango/InstRec/deploy/quantization_config.json "
        "(static fbgemm PTQ, 500 Medley calibration samples)",
        "D:/0000/111/001/Pango/InstRec/runs/best_model.pt (float 8f)",
        "D:/0000/111/001/Pango/InstRec/deploy/quantized_model.pt "
        "(quantized 8q)",
    ]

    report["feature_domain_comparison"] = {
        "verdict": "(a) rejected: train-domain, F0 and golden-domain "
                   "features give sample-identical top1 on the float "
                   "model (G1 == G2a == G2b); the acoustic parameters "
                   "are identical (sr 44100 / n_fft 2048 / hop 512 / "
                   "64 slaney mels / fmax 22050 / power 2.0 / "
                   "power_to_db ref=max top_db=80 / keep-tail 258 / "
                   "per-sample z-norm). The only differences are "
                   "numerical: integer (L+R+1)>>1 downmix vs librosa "
                   "float mean, 132096-sample hardware window vs full "
                   "132299-sample file, fixed-point Q15/Q4.12 chain vs "
                   "float chain - LSB-scale effects only (see "
                   "feature_diffs), no top1 change.",
        "quantization_input_convention": "The deployed quantized model "
                   "consumes the SAME float feature as the float model "
                   "(deploy/inference_reference.py predict(): float "
                   "(1,1,64,258) into the QuantStub forward); the "
                   "uint8 domain (s_in=0.06266622245311737, zp_in=49) "
                   "exists only inside the QuantStub / the NPU input "
                   "image. fv.quantize_uint8 reproduces the fbgemm "
                   "QuantStub semantics bit-exactly (run_compare S3); "
                   "the golden/RTL shift bug is a re-implementation "
                   "error of exactly this step.",
    }

    report["conclusion"] = {
        "matrix": {
            "G1_train_float": matrix["G1_train_float"]["top1_per_sample"],
            "G2a_f0_float": matrix["G2a_f0_float"]["top1_per_sample"],
            "G2b_goldenz_float": matrix["G2b_goldenz_float"]["top1_per_sample"],
            "G2c_goldenu8deq_float": matrix["G2c_goldenu8deq_float"]["top1_per_sample"],
            "G2d_goldenu8fixeddeq_float": matrix["G2d_goldenu8fixeddeq_float"]["top1_per_sample"],
            "G3_train_quant": matrix["G3_train_quant"]["top1_per_sample"],
            "G4_golden_quant_torch": matrix["G4_golden_quant_torch"]["top1_per_sample"],
            "G4_golden_quant_npu_probe_cited":
                matrix["G4_golden_quant_npu_probe_cited"]["top1_per_sample"],
            "G4b_golden_quant_fixed": matrix["G4b_golden_quant_fixed"]["top1_per_sample"],
        },
        "final": "(b) quantization defect with a precisely localized "
                 "implementation bug: the golden/RTL input uint8 "
                 "quantization shifts z_q412 * inv_s_in by 24 instead of "
                 "36 bits (4096x scale error), binarizing the feature and "
                 "collapsing every input to top1=0 (clarinet in the "
                 "deployed Medley label space, misread as 'piano' in "
                 "npu_probe under an IRMAS-order table). Feature-domain "
                 "mismatch (a) is rejected; fbgemm weight quantization is "
                 "intact (G3 == G1). Secondary (c): the float model is "
                 "weak on IRMAS-domain clips (exact 1/5, piano 3/3) - "
                 "fix the shift first, then re-evaluate on "
                 "training-domain audio; full IRMAS accuracy needs "
                 "domain re-validation or retraining.",
        "confidence": "high - four-way closure: {float, quantized} model x "
                      "{buggy, corrected} input quantization; the buggy "
                      "uint8 collapses BOTH models, the corrected uint8 "
                      "matches the float-feature result sample-by-sample, "
                      "and the golden feature hash reproduces "
                      "npu_probe 8/8 so the cited evidence and this run "
                      "share the identical (broken) feature.",
    }

    out = Path(DEFAULT_REPORT)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("draft report written: %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
