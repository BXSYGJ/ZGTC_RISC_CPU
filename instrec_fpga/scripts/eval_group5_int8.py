"""Evaluate the group5 INT8 contract against float on the held-out val split.

Runs the SAME frozen float model (models/group5_v3_float_20261102) and the
bit-exact INT8 integer simulator (golden_pipeline_group5.npu_forward_group5,
weights streamed back from the IRW1 image) over all 8906 val rows, then
reports:

  a) activity head: per-class precision/recall/F1 @0.5, subset accuracy,
     micro/macro F1 (percussion is called out separately: only ~157 train /
     389 val positives);
  b) dominance head MAE on dominance_mask==1 rows (float-vs-GT,
     int8-vs-GT, int8-vs-float);
  c) final dominant-group decision accuracy: dominance softmax masked by
     activity>0.5 and renormalized; no active group -> "no dominant" (never
     forced).  Identical post-processing for float and INT8;
  d) no-active-sample ratio and the float/INT8 agreement on that decision.

Acceptance: dominant-group agreement >= 0.97 AND macro-F1 drop <= 0.02.

Usage: python scripts/eval_group5_int8.py [--limit N] [--batch 32]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import torch

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from golden_pipeline_group5 import (  # noqa: E402
    DEFAULT_CACHE_DIR, DEFAULT_MODEL_DIR, GROUP_NAMES, load_float_model,
    load_weights_from_image, npu_forward_group5,
)

DEFAULT_CONTRACT = SCRIPTS_DIR / "outputs" / "group5_contract.json"
DEFAULT_IMAGE = SCRIPTS_DIR / "outputs" / "group5_weights_image.bin"
DEFAULT_REPORT = PROJECT_DIR / "reports" / "group5_int8_calibration_20261103.json"

PERC_INDEX = 3  # percussion column (called out in the verdict)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Shared post-processing (identical for float and INT8).
# ---------------------------------------------------------------------------
def sigmoid_stable(x: np.ndarray) -> np.ndarray:
    out = np.empty_like(x)
    pos = x >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-x[pos]))
    ex = np.exp(x[~pos])
    out[~pos] = ex / (1.0 + ex)
    return out


def softmax_rows(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def postprocess(act_logits: np.ndarray, dom_logits: np.ndarray) -> dict:
    """Activity sigmoid + dominance softmax, masked by activity>0.5.

    No active group -> dominance stays all-zero ("no dominant" class -1),
    exactly the freeze_group5_reference.py semantics.
    """
    act_prob = sigmoid_stable(act_logits)
    active = act_prob > 0.5
    dom_prob = softmax_rows(dom_logits)
    masked = dom_prob * active
    totals = masked.sum(axis=1, keepdims=True)
    dom_final = np.where(totals > 0, masked / np.maximum(totals, 1e-12), 0.0)
    has_dominant = dom_final.sum(axis=1) > 0
    dominant = np.where(has_dominant, dom_final.argmax(axis=1), -1)
    return {
        "act_prob": act_prob, "active": active,
        "dom_prob": dom_prob, "dom_final": dom_final,
        "dominant": dominant.astype(np.int64),
        "no_active": ~active.any(axis=1),
    }


# ---------------------------------------------------------------------------
# Metrics.
# ---------------------------------------------------------------------------
def per_class_prf(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Per-class precision/recall/F1 + micro/macro/subject accuracy."""
    tp = ((y_pred == 1) & (y_true == 1)).sum(axis=0)
    fp = ((y_pred == 1) & (y_true == 0)).sum(axis=0)
    fn = ((y_pred == 0) & (y_true == 1)).sum(axis=0)
    prec = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), 0.0)
    rec = np.where(tp + fn > 0, tp / np.maximum(tp + fn, 1), 0.0)
    f1 = np.where(prec + rec > 0, 2 * prec * rec / np.maximum(prec + rec, 1e-12), 0.0)
    micro_p = tp.sum() / max(tp.sum() + fp.sum(), 1)
    micro_r = tp.sum() / max(tp.sum() + fn.sum(), 1)
    micro_f1 = 2 * micro_p * micro_r / max(micro_p + micro_r, 1e-12)
    subset_acc = float((y_pred == y_true).all(axis=1).mean())
    return {
        "per_class": {
            GROUP_NAMES[c]: {
                "precision": float(prec[c]), "recall": float(rec[c]),
                "f1": float(f1[c]),
                "n_positive": int(y_true[:, c].sum()),
            } for c in range(y_true.shape[1])
        },
        "micro_f1": float(micro_f1),
        "macro_f1": float(f1.mean()),
        "subset_accuracy": subset_acc,
    }


def dominance_metrics(pp: dict, dom_gt: np.ndarray, mask_rows: np.ndarray,
                      other_pp: dict | None = None) -> dict:
    """MAE of the final (masked+renormalized) dominance vs GT on masked rows."""
    out = {}
    if mask_rows.any():
        diff = np.abs(pp["dom_final"][mask_rows] - dom_gt[mask_rows])
        out["mae_vs_gt"] = float(diff.mean())
        out["max_abs_err_vs_gt"] = float(diff.max())
    else:
        out["mae_vs_gt"] = None
    if other_pp is not None and mask_rows.any():
        out["mae_vs_other"] = float(np.abs(
            pp["dom_final"][mask_rows] - other_pp["dom_final"][mask_rows]).mean())
    return out


def dominant_group_metrics(pp: dict, dom_gt: np.ndarray, mask_rows: np.ndarray):
    acc = None
    if mask_rows.any():
        gt_dom = dom_gt[mask_rows].argmax(axis=1)
        acc = float((pp["dominant"][mask_rows] == gt_dom).mean())
    return {"accuracy_on_masked_rows": acc}


# ---------------------------------------------------------------------------
# Forward passes.
# ---------------------------------------------------------------------------
def float_forward(model, feats_m, rows: np.ndarray, batch: int = 256) -> tuple:
    acts, doms = [], []
    with torch.no_grad():
        for i in range(0, len(rows), batch):
            x = torch.from_numpy(
                np.asarray(feats_m[rows[i:i + batch]], dtype=np.float32))[:, None]
            a, d = model.forward_dual(x)
            acts.append(a.numpy())
            doms.append(d.numpy())
    return np.concatenate(acts), np.concatenate(doms)


def int8_forward(contract: dict, weights: dict, feats_m, rows: np.ndarray,
                 batch: int = 32) -> tuple:
    acts, doms = [], []
    for i in range(0, len(rows), batch):
        x = np.asarray(feats_m[rows[i:i + batch]], dtype=np.float32)[:, None]
        out = npu_forward_group5(x, contract, weights)
        acts.append(out["act_logits"])
        doms.append(out["dom_logits"])
    return np.concatenate(acts), np.concatenate(doms)


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Group5 INT8 vs float evaluation on the val split.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-float", type=int, default=256)
    parser.add_argument("--batch-int8", type=int, default=32)
    parser.add_argument("--limit", type=int, default=0,
                        help="debug: evaluate only the first N val rows")
    args = parser.parse_args(argv)

    with open(args.contract, "r", encoding="utf-8") as fh:
        contract = json.load(fh)
    weights = load_weights_from_image(contract, args.image)

    model, _, _ = load_float_model(args.model_dir)
    with open(args.cache_dir / "split.json", "r", encoding="utf-8") as fh:
        split = json.load(fh)
    val_idx = np.asarray(split["val_indices"], dtype=np.int64)
    feats_m = np.load(args.cache_dir / "all_features.npy", mmap_mode="r")
    labels = np.load(args.cache_dir / "labels.npy")
    dom_gt = np.load(args.cache_dir / "dominance.npy")
    dmask = np.load(args.cache_dir / "dominance_mask.npy").astype(bool)

    if args.limit > 0:
        val_idx = val_idx[:args.limit]

    t0 = time.time()
    print(f"[float] forward over {len(val_idx)} val rows ...")
    act_f, dom_f = float_forward(model, feats_m, val_idx, args.batch_float)
    t_float = time.time() - t0
    print(f"[float] done in {t_float:.1f}s")

    t0 = time.time()
    print(f"[int8 ] forward over {len(val_idx)} val rows ...")
    act_i, dom_i = int8_forward(contract, weights, feats_m, val_idx,
                                args.batch_int8)
    t_int8 = time.time() - t0
    print(f"[int8 ] done in {t_int8:.1f}s")

    y_true = (labels[val_idx] > 0.5)
    dom_gt = dom_gt[val_idx]   # val subset of the full-cache arrays
    mask_rows = dmask[val_idx]

    pp_f = postprocess(act_f, dom_f)
    pp_i = postprocess(act_i, dom_i)

    m_f = per_class_prf(y_true, pp_f["active"])
    m_i = per_class_prf(y_true, pp_i["active"])
    dmacro = m_i["macro_f1"] - m_f["macro_f1"]

    dom_m_f = dominance_metrics(pp_f, dom_gt, mask_rows)
    dom_m_i = dominance_metrics(pp_i, dom_gt, mask_rows, pp_f)
    dg_f = dominant_group_metrics(pp_f, dom_gt, mask_rows)
    dg_i = dominant_group_metrics(pp_i, dom_gt, mask_rows)

    agreement = float((pp_f["dominant"] == pp_i["dominant"]).mean())
    no_active_f = float(pp_f["no_active"].mean())
    no_active_i = float(pp_i["no_active"].mean())
    no_active_agree = float((pp_f["no_active"] == pp_i["no_active"]).mean())
    act_pred_agree = float((pp_f["active"] == pp_i["active"]).all(axis=1).mean())

    per_class_table = {}
    for c, name in enumerate(GROUP_NAMES):
        per_class_table[name] = {
            "n_positive": int(y_true[:, c].sum()),
            "precision": {"float": m_f["per_class"][name]["precision"],
                          "int8": m_i["per_class"][name]["precision"]},
            "recall": {"float": m_f["per_class"][name]["recall"],
                       "int8": m_i["per_class"][name]["recall"]},
            "f1": {"float": m_f["per_class"][name]["f1"],
                   "int8": m_i["per_class"][name]["f1"],
                   "delta": m_i["per_class"][name]["f1"] - m_f["per_class"][name]["f1"]},
        }

    passed = (agreement >= 0.97) and (dmacro >= -0.02)

    report = {
        "report_id": "group5_int8_calibration_20261103",
        "date": "2026-11-03",
        "purpose": "five-group dual-head model INT8 contract acceptance "
                   "evaluation on the held-out val split",
        "inputs": {
            "contract": str(args.contract),
            "contract_sha256": sha256_file(args.contract),
            "weights_image": str(args.image),
            "weights_image_sha256": sha256_file(args.image),
            "float_state_sha256": sha256_file(args.model_dir / "float_state.npz"),
            "reference_vectors_sha256": sha256_file(
                args.model_dir / "reference_vectors.npz"),
            "features_sha256": contract["calibration"]["features_sha256"],
            "split_json_sha256": sha256_file(args.cache_dir / "split.json"),
            "val_rows": int(len(val_idx)),
            "val_rows_full": int(split["n_val"]),
            "val_subset_note": "full val split" if len(val_idx) == split["n_val"]
                               else f"LIMITED to first {len(val_idx)} rows (debug)",
            "calib_rows_used": contract["calibration"]["calib_rows_used"],
            "calib_method": contract["calibration"]["method"],
        },
        "commands": [
            "python scripts/golden_pipeline_group5.py",
            "python scripts/eval_group5_int8.py",
        ],
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__, "torch": torch.__version__,
            "platform": platform.platform(),
        },
        "timing_sec": {"float_forward": round(t_float, 1),
                       "int8_forward": round(t_int8, 1)},
        "metrics": {
            "activity": {
                "float": m_f, "int8": m_i,
                "macro_f1_delta": dmacro,
                "per_class": per_class_table,
                "percussion_callout": {
                    "note": "sparse class: ~157 train / 389 val positives",
                    "f1_float": m_f["per_class"]["percussion"]["f1"],
                    "f1_int8": m_i["per_class"]["percussion"]["f1"],
                    "recall_float": m_f["per_class"]["percussion"]["recall"],
                    "recall_int8": m_i["per_class"]["percussion"]["recall"],
                },
                "row_level_active_set_agreement": act_pred_agree,
            },
            "dominance": {
                "masked_rows": int(mask_rows.sum()),
                "mae_float_vs_gt": dom_m_f.get("mae_vs_gt"),
                "mae_int8_vs_gt": dom_m_i.get("mae_vs_gt"),
                "mae_int8_vs_float": dom_m_i.get("mae_vs_other"),
                "max_abs_err_float_vs_gt": dom_m_f.get("max_abs_err_vs_gt"),
                "max_abs_err_int8_vs_gt": dom_m_i.get("max_abs_err_vs_gt"),
            },
            "dominant_group": {
                "definition": "dominance softmax masked by activity>0.5 and "
                              "renormalized; no active group -> -1 ('no "
                              "dominant', never forced)",
                "accuracy_float": dg_f["accuracy_on_masked_rows"],
                "accuracy_int8": dg_i["accuracy_on_masked_rows"],
                "agreement_all_val_rows": agreement,
            },
            "no_active": {
                "ratio_float": no_active_f,
                "ratio_int8": no_active_i,
                "binary_agreement": no_active_agree,
                "n_no_active_float": int(pp_f["no_active"].sum()),
                "n_no_active_int8": int(pp_i["no_active"].sum()),
            },
            "logit_domain": {
                "max_abs_dlogit_activity": float(
                    np.abs(act_i - act_f).max()),
                "mean_abs_dlogit_activity": float(
                    np.abs(act_i - act_f).mean()),
                "max_abs_dlogit_dominance": float(
                    np.abs(dom_i - dom_f).max()),
                "mean_abs_dlogit_dominance": float(
                    np.abs(dom_i - dom_f).mean()),
            },
        },
        "acceptance": {
            "criteria": "dominant-group agreement >= 0.97 AND macro F1 "
                        "drop <= 0.02",
            "dominant_agreement": agreement,
            "macro_f1_float": m_f["macro_f1"],
            "macro_f1_int8": m_i["macro_f1"],
            "macro_f1_delta": dmacro,
            "passed": passed,
        },
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(json.dumps({
        "val_rows": len(val_idx),
        "macro_f1": {"float": m_f["macro_f1"], "int8": m_i["macro_f1"],
                     "delta": dmacro},
        "micro_f1": {"float": m_f["micro_f1"], "int8": m_i["micro_f1"]},
        "subset_acc": {"float": m_f["subset_accuracy"],
                       "int8": m_i["subset_accuracy"]},
        "percussion_f1": {"float": m_f["per_class"]["percussion"]["f1"],
                          "int8": m_i["per_class"]["percussion"]["f1"]},
        "dom_mae": {"float_vs_gt": dom_m_f.get("mae_vs_gt"),
                    "int8_vs_gt": dom_m_i.get("mae_vs_gt"),
                    "int8_vs_float": dom_m_i.get("mae_vs_other")},
        "dominant_acc": {"float": dg_f["accuracy_on_masked_rows"],
                         "int8": dg_i["accuracy_on_masked_rows"],
                         "agreement": agreement},
        "no_active": {"float": no_active_f, "int8": no_active_i,
                      "agreement": no_active_agree},
        "PASSED": passed,
        "report": str(args.report),
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
