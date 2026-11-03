"""Group5 (five instrument groups) INT8 quantization contract generator.

Methodology is aligned with the 8-class migration (scripts/golden_pipeline.py
+ scripts/gen_weight_image.py, spec refs tasks.md T-GP-03/T-GP-05) but EVERY
quantization constant is re-calibrated on the group5_v3_float_20261102 float
model + group5_cache_v3 TRAIN split.  No 8-class constant is reused.

Contract semantics pinned by this tool
--------------------------------------
* BN fold (eval semantics): w_fold = w * gamma / sqrt(var + eps),
  b_fold = b * gamma/sqrt(var+eps) + beta - gamma*mean/sqrt(var+eps).
* Weight: per-channel SYMMETRIC int8 in [-127, 127], s_w[c] = max|w_fold[c]|/127,
  round-half-even element rounding.
* Activations: asymmetric quint8.  MinMax calibration on a stratified TRAIN
  split sample, with 0 forced representable (min <-- min(min,0),
  max <-- max(max,0), fbgemm observer parity): s = (max-min)/255,
  zp = clamp(RHE(-min/s), 0, 255).
* Input feat: asymmetric quint8 over the float z-domain feature, calibrated
  on the FULL train split min/max (streamed mmap scan).  Quantization uses
  the integer inv_s_in = round(2^24/s_in) Q8.24 path (RTL parity):
  x_u8 = sat_u8(RHE(x * inv_s_in >> 24) + zp_in).
* requant (8-class R-C lesson): y = sat_u8(RHE(acc_s32 * M[c] >>> shift[c])
  + zp_out), M[c] = round(s_w[c]*s_in/s_out * 2^shift[c]) in [2^30, 2^31).
  ROUND-HALF-EVEN is mandatory; truncating shifts amplify to +/-32 LSB/layer.
* bias_int32 = RHE(b_fold / (s_in * s_w[c])) rebuilt from float_state.npz
  (the 8-class astype(np.int32) corruption must never be repeated).
* GAP: the 5-class pool4 map is 4x8 = 32 taps (the 8-class map was 8x16=64
  with >>6).  Contract: round_half_even(sum >> 5), identity quantization
  (fc1 / dom_fc1 input domain == conv4 output domain).
* Dual heads: activity fc1/fc2 and dominance dom_fc1/dom_fc2 both consume
  the GAP vector and serialize over the same NPU fc engine; their weight
  image segments are laid out separately (activity head first).

Integer bit-exactness strategy
-------------------------------
MAC accumulation uses float64 BLAS matmul + rint() back to int64.  This is
EXACT: every product (x-zp)*w is an integer <= 255*127 = 32385 (float64
exact), partial sums stay below 2^27 (1728 taps max), so the accumulated
floating error is < 1e-4 LSB and rint recovers the unique integer.  A
cross-check against a pure int64 tensordot path runs on every invocation.

Usage
-----
  python scripts/golden_pipeline_group5.py                 # calibrate + emit
  python scripts/golden_pipeline_group5.py --calib-n 4000  # faster calibration
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
import torch

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPTS_DIR.parent
DEFAULT_MODEL_DIR = PROJECT_DIR / "models" / "group5_v3_float_20261102"
DEFAULT_CACHE_DIR = Path("D:/0000/111/001/Pango/InstRec/data/group5_cache_v3")
DEFAULT_OUT_DIR = SCRIPTS_DIR / "outputs"
DEFAULT_WEIGHTS_DIR = PROJECT_DIR / "deploy" / "weights_group5"

GENERATOR_NAME = "golden_pipeline_group5.py"
SPEC_REFS = (
    "8-class methodology: tasks.md T-GP-03/T-GP-05, design.md 4.3/5.2/3.7; "
    "group5 migration step 1 (numeric contract, 2026-11-02)"
)

GROUP_NAMES = ["strings", "woodwinds", "brass", "percussion", "keys"]
GROUP_NAMES_ZH = ["弦乐组", "木管组", "铜管组", "打击乐组", "键盘组"]

# ---------------------------------------------------------------------------
# Weight image constants (aligned with the 8-class gen_weight_image.py /
# design.md 5.2 layout; 8 layers instead of 6).
# ---------------------------------------------------------------------------
IMAGE_MAGIC = b"IRW1"
HEADER_BYTES = 32
CONTRACT_ENTRY_BYTES = 64
CONTRACT_TABLE_OFFSET = HEADER_BYTES          # 0x0020
FIRST_LAYER_OFFSET = 0x400                    # 0x400: 8x64B table + header
ALIGN_BYTES = 32                              # DDR3 256-bit word alignment
GROUP_CHANNELS = 16
NUM_LAYERS = 8
FORMAT_VERSION = 1
# Planned DDR3 base for the group5 image.  The 8-class image occupies
# 0x00100000..0x001A8DE0; 0x00200000 keeps the two images disjoint if both
# are staged.  Final address map is decided by the M2 weight_loader port.
DDR3_WEIGHT_BASE = 0x0020_0000

M_MIN = 1 << 30
M_MAX = 1 << 31
QUANT_IN_FRAC_BITS = 24                       # Q8.24 inv_s_in (design.md 3.7)
GAP_SHIFT = 5                                 # 4x8 = 32 taps (8-class: >>6)
GAP_GEOMETRY = (4, 8)

LAYER_SPECS = (
    # name, type, weight_shape, in_shape, out_shape
    ("conv1", "conv", (48, 1, 3, 3), (1, 64, 130), (48, 64, 130)),
    ("conv2", "conv", (96, 48, 3, 3), (48, 32, 65), (96, 32, 65)),
    ("conv3", "conv", (192, 96, 3, 3), (96, 16, 32), (192, 16, 32)),
    ("conv4", "conv", (256, 192, 3, 3), (192, 8, 16), (256, 8, 16)),
    ("fc1", "fc", (128, 256), (256,), (128,)),
    ("fc2", "fc", (5, 128), (128,), (5,)),
    ("dom_fc1", "fc", (128, 256), (256,), (128,)),
    ("dom_fc2", "fc", (5, 128), (128,), (5,)),
)

# Calibration hooks: quantized-domain output of each layer <-> float module.
RELU_HOOK_LAYERS = (
    ("conv1", "relu1"), ("conv2", "relu2"), ("conv3", "relu3"),
    ("conv4", "relu4"), ("fc1", "relu_fc"), ("dom_fc1", "dom_relu"),
)


# ---------------------------------------------------------------------------
# Small helpers (semantics copied from the 8-class golden_pipeline.py /
# gen_weight_image.py so this module stays self-contained).
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def round_half_even_shift(x: np.ndarray, k) -> np.ndarray:
    """Bit-level round-half-to-even division by 2^k (signed, vectorized k)."""
    sign = x < 0
    av = np.where(sign, -x, x).astype(np.int64)
    if np.isscalar(k):
        kk = np.int64(k)
    else:
        kk = np.asarray(k, dtype=np.int64)
    q = np.right_shift(av, kk)
    rem = np.bitwise_and(av, (np.int64(1) << kk) - np.int64(1))
    half = np.int64(1) << (kk - np.int64(1))
    inc = (rem > half) | ((rem == half) & ((q & np.int64(1)) == np.int64(1)))
    q = q + inc.astype(np.int64)
    return np.where(sign, -q, q)


def rhe_float(x: np.ndarray) -> np.ndarray:
    """Round-half-to-even for float arrays (numpy rint semantics)."""
    return np.rint(x)


def compute_m_shift(ratio: float) -> tuple:
    """(M, shift) with M = round(ratio * 2^shift) in [2^30, 2^31) (Q0.31).

    Copied from gen_weight_image.py (integer correction loops avoid float
    log2 boundary hazards).
    """
    if not (ratio > 0.0):
        raise ValueError(f"ratio must be positive, got {ratio!r}")
    if round(ratio) >= M_MAX:
        raise ValueError(f"ratio={ratio!r} >= 2^31")
    if round(ratio * 2.0 ** 63) < M_MIN:
        raise ValueError(f"ratio={ratio!r} too small for shift<=63")
    shift = int(math.floor(math.log2(float(M_MAX) / ratio))) + 1
    while round(ratio * 2.0 ** shift) >= M_MAX or shift > 63:
        shift -= 1
    while round(ratio * 2.0 ** (shift + 1)) < M_MAX and shift < 63:
        shift += 1
    while round(ratio * 2.0 ** shift) < M_MIN and shift < 63:
        shift += 1
    m = int(round(ratio * 2.0 ** shift))
    if not (M_MIN <= m < M_MAX):
        raise ValueError(f"M={m} shift={shift} out of [2^30,2^31) for {ratio!r}")
    if not (0 <= shift <= 63):
        raise ValueError(f"shift={shift} exceeds 6-bit range")
    return m, shift


def choose_inv_s_in(s_in: float) -> dict:
    """inv_s_in Q-format selection (design.md 3.7, copied semantics)."""
    q16 = int(round(2 ** 16 / s_in))
    if 0 < q16 <= 0xFFFF:
        return {"format": "Q16.16", "bits": 16, "value": q16}
    q24 = int(round(2 ** 24 / s_in))
    if 0 < q24 <= 0x7FFFFFFF:
        return {"format": "Q8.24", "bits": 32, "value": q24}
    raise ValueError(f"inv_s_in for s_in={s_in!r} overflows Q8.24 s32")


def interleave_group_major(weight_2d: np.ndarray,
                           group_channels: int = GROUP_CHANNELS) -> np.ndarray:
    """Reorder (Cout, K) int8 weights into 16-channel group-major order."""
    cout, k = weight_2d.shape
    out = np.empty(cout * k, dtype=np.int8)
    pos = 0
    for g in range(0, cout, group_channels):
        gc = min(group_channels, cout - g)
        block = weight_2d[g:g + gc, :]
        out[pos:pos + gc * k] = block.T.reshape(-1)
        pos += gc * k
    assert pos == cout * k
    return out


def _deinterleave_group_major(w_bytes: np.ndarray, cout: int, k: int) -> np.ndarray:
    """Inverse of interleave_group_major (natural (Cout, K) order)."""
    out = np.empty((cout, k), dtype=np.int8)
    pos = 0
    for g in range(0, cout, GROUP_CHANNELS):
        gc = min(GROUP_CHANNELS, cout - g)
        out[g:g + gc, :] = w_bytes[pos:pos + gc * k].reshape(k, gc).T
        pos += gc * k
    assert pos == w_bytes.size
    return out


def segment_checksum_128(payload: bytes) -> bytes:
    """128-bit chunk-sum checksum (design.md 6.4 weak-sha board verify)."""
    acc = 0
    for i in range(0, len(payload), 16):
        chunk = payload[i:i + 16]
        if len(chunk) < 16:
            chunk = chunk + b"\x00" * (16 - len(chunk))
        acc = (acc + int.from_bytes(chunk, "little")) % (1 << 128)
    return acc.to_bytes(16, "little")


def pack_contract_entry(layer: dict) -> bytes:
    """Pack one 64-byte binary layer-contract entry (8-class field layout).

    Deviation from the 8-class pack format: zp_in/zp_out use UNSIGNED
    bytes ('B') instead of the 8-class signed 'b'.  The quint8 zero-point
    domain is [0, 255] and the 5-class fc2/dom_fc2 heads legitimately
    calibrate zp_out > 127 (wide multi-label logit ranges); the 8-class
    image never hit this because all its zero points stayed <= 57.
    """
    dtype_code = 0 if layer["activation_dtype"] == "torch.quint8" else 1
    in_c, in_h, in_w = layer["in_shape_padded"]
    out_c, out_h, out_w = layer["out_shape_padded"]
    entry = struct.pack(
        "<HBBHHIIIIIIBBBBHHHHIHHIII",
        0x4C43, layer["layer_id"],
        0 if layer["layer_type"] == "conv" else 1,
        layer["num_groups"], layer["num_channels"],
        layer["image_offset"], layer["segment_bytes"],
        layer["weight_bytes"], layer["bias_off"], layer["m_off"],
        layer["shift_off"],
        layer["zp_in"], layer["zp_out"], dtype_code,
        layer["last_group_channels"],
        in_c, in_w, out_c, out_w, layer["weight_k"],
        in_h, out_h,
        0, 0, 0,
    )
    assert len(entry) == CONTRACT_ENTRY_BYTES
    return entry


# Semantic saturation bounds for the output-head logits (round-2 calibration
# variant "sat").  These trim the MinMax output range where the prediction
# semantics are provably unchanged:
#   * activity head: |logit| > 14 -> sigmoid in [8.3e-7, 1-8.3e-7], six orders
#     of magnitude away from the 0.5 decision threshold; clipping keeps the
#     sigmoid monotone, so no prediction can flip.
#   * dominance head: softmax is shift-invariant and only logit DIFFERENCES
#     matter; a difference of -24 corresponds to a relative weight of
#     e^-24 = 3.8e-11 (< 4e-10 even with all four other classes at the
#     boundary), so trimming the range to a 24-wide window anchored at the
#     observed max loses nothing, and clipping is monotone (argmax order
#     preserved).
# Both trims shrink s_out by ~3x versus raw MinMax, which was dominated by
# information-free saturated logits (observed fc2 range [-66, +28]).
ACT_SAT_LOGIT = 14.0
DOM_SPAN = 24.0

# Input-feature semantic saturation bound.  The float z-domain feature has a
# long positive tail (train min/max [-4.09, +16.93]) whose extremes are
# information-free for the network (val-set elements above +8: < 1e-5), and
# the 8-class deployment already saturates its fixed-point z container at
# +/-8 (int16 Q4.12 sat16).  Clipping the calibration domain to +/-8 both
# matches the future 5-class mel fixed-point semantics and shrinks s_in
# 1.7x.  The u8 saturation in quantize_input_feat realizes the clip.
FEAT_SAT = 8.0


# ---------------------------------------------------------------------------
# Float model loading and BN folding.
# ---------------------------------------------------------------------------
def load_float_model(model_dir: Path):
    """Load DualHeadInstrumentCNN from the frozen model directory (read-only)."""
    spec = importlib.util.spec_from_file_location(
        "group5_model_source", model_dir / "model_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.DualHeadInstrumentCNN(num_classes=5)
    state_np = np.load(model_dir / "float_state.npz")
    state = {k: torch.from_numpy(np.asarray(state_np[k])) for k in state_np.files}
    model.load_state_dict(state, strict=True)
    model.eval()
    bn_eps = float(model.bn1.eps)
    return model, {k: np.asarray(state_np[k]) for k in state_np.files}, bn_eps


def bn_fold(state: dict, bn_eps: float) -> dict:
    """Fold BatchNorm into the conv weights/biases (eval semantics).

    w_fold = w * gamma/sqrt(var+eps)
    b_fold = b*gamma/sqrt(var+eps) + beta - gamma*mean/sqrt(var+eps)
    """
    folded = {}
    for i in (1, 2, 3, 4):
        gamma = state[f"bn{i}.weight"].astype(np.float64)
        beta = state[f"bn{i}.bias"].astype(np.float64)
        mean = state[f"bn{i}.running_mean"].astype(np.float64)
        var = state[f"bn{i}.running_var"].astype(np.float64)
        inv_std = gamma / np.sqrt(var + bn_eps)
        w = state[f"conv{i}.weight"].astype(np.float64)
        b = state[f"conv{i}.bias"].astype(np.float64)
        folded[f"conv{i}"] = {
            "w": w * inv_std[:, None, None, None],
            "b": b * inv_std + (beta - inv_std * mean),
        }
    for name in ("fc1", "fc2", "dom_fc1", "dom_fc2"):
        folded[name] = {
            "w": state[f"{name}.weight"].astype(np.float64),
            "b": state[f"{name}.bias"].astype(np.float64),
        }
    return folded


def quantize_weight_symmetric(w2d: np.ndarray) -> tuple:
    """Per-channel symmetric int8 [-127,127]: s_w = max|w[c]|/127, RHE."""
    max_abs = np.abs(w2d).max(axis=1)
    s_w = np.where(max_abs > 0, max_abs / 127.0, 1.0)
    q = np.clip(rhe_float(w2d / s_w[:, None]), -127.0, 127.0).astype(np.int8)
    return q, s_w.astype(np.float64)


# ---------------------------------------------------------------------------
# Activation calibration (fbgemm MinMax observer parity).
# ---------------------------------------------------------------------------
def qparams_from_minmax(mn: float, mx: float, clip_lo: float = None,
                        clip_hi: float = None) -> tuple:
    """Asymmetric quint8 qparams with 0 kept representable (fbgemm parity).

    Optional semantic saturation bounds (clip_lo/clip_hi) trim the observed
    MinMax range where the downstream nonlinearity is already saturated --
    lossless for the prediction semantics (see ACT_SAT_LOGIT / DOM_SPAN).
    """
    mn = min(mn, 0.0)
    mx = max(mx, 0.0)
    if clip_lo is not None:
        mn = max(mn, clip_lo)
    if clip_hi is not None:
        mx = min(mx, clip_hi)
    if not (mn <= 0.0 <= mx):
        raise ValueError(f"quantum range [{mn},{mx}] does not contain 0")
    if mx == mn:
        s = 1.0
    else:
        s = (mx - mn) / 255.0
    zp = int(np.clip(rhe_float(np.float64(-mn / s)), 0.0, 255.0))
    return float(s), zp


def stratified_sample(labels_tr: np.ndarray, n_target: int, seed: int) -> np.ndarray:
    """Stratified train-split sample by activity label signature.

    All percussion-positive rows are kept (only ~157 in train); the rest is
    sampled proportionally per 5-bit label signature.
    """
    rng = np.random.default_rng(seed)
    sig = labels_tr > 0.5
    key = sig.astype(np.int64) @ np.int64([16, 8, 4, 2, 1])
    perc = np.flatnonzero(sig[:, 3])
    rest = np.flatnonzero(~sig[:, 3])
    parts = [perc]
    if len(rest) > 0 and n_target > len(perc):
        keys = key[rest]
        budget = n_target - len(perc)
        for k in np.unique(keys):
            cand = rest[keys == k]
            take = max(1, int(round(budget * len(cand) / len(rest))))
            take = min(take, len(cand))
            parts.append(rng.choice(cand, size=take, replace=False))
    idx = np.unique(np.concatenate(parts)) if len(parts) > 1 else parts[0]
    return np.sort(np.asarray(idx, dtype=np.int64))


def full_feature_minmax(feats_m, rows: np.ndarray, block: int = 4096) -> tuple:
    """Exact min/max of the float feature over the given rows (mmap stream)."""
    gmin, gmax = float("inf"), float("-inf")
    for i in range(0, len(rows), block):
        chunk = np.asarray(feats_m[rows[i:i + block]], dtype=np.float32)
        gmin = min(gmin, float(chunk.min()))
        gmax = max(gmax, float(chunk.max()))
    return gmin, gmax


class MaxObserver:
    """Streaming element-level histogram observer for percentile clipping.

    Tracks the upper-tail distribution of non-negative (post-ReLU)
    activations so the calibration max can be set to an element percentile
    instead of the raw global max (which long-tailed conv maps inflate
    1.3..1.9x, thinning every downstream scale).
    """

    def __init__(self, nbins: int = 4096) -> None:
        self.nbins = nbins
        self.counts = None
        self.hi = 1.0

    def update(self, arr: np.ndarray) -> None:
        m = float(arr.max())
        if self.counts is None:
            self.hi = max(m, 1e-6) * 1.01
            self.counts = np.zeros(self.nbins, dtype=np.int64)
        elif m > self.hi:
            new_hi = m * 1.01
            idx = np.minimum(
                (np.arange(self.nbins, dtype=np.float64) * self.hi
                 / new_hi).astype(np.int64), self.nbins - 1)
            merged = np.zeros(self.nbins, dtype=np.int64)
            np.add.at(merged, idx, self.counts)
            self.counts = merged
            self.hi = new_hi
        h, _ = np.histogram(arr, bins=self.nbins, range=(0.0, self.hi))
        self.counts += h.astype(np.int64)

    def percentile_max(self, q: float) -> float:
        """Upper-edge of the bin containing the q-th element percentile."""
        if self.counts is None:
            raise RuntimeError("observer never saw data")
        total = int(self.counts.sum())
        target = total * q / 100.0
        cum = np.cumsum(self.counts)
        b = int(np.searchsorted(cum, target))
        b = min(b, self.nbins - 1)
        return float((b + 1) / self.nbins * self.hi)

    def raw_max(self) -> float:
        return float(self.hi / 1.01)


def calibrate_activations(model, feats_m, calib_rows: np.ndarray,
                          batch: int = 256,
                          histogram_layers: tuple = (),
                          feat_clip: tuple = None) -> dict:
    """Collect per-layer observed min/max over the calibration rows.

    Quantized-domain outputs are the post-ReLU conv/fc1/dom_fc1 outputs and
    the raw fc2/dom_fc2 logits (forward_dual return values).  For the
    layers named in histogram_layers an element-level MaxObserver also
    accumulates the upper-tail distribution for percentile clipping.
    feat_clip=(lo, hi) saturates the calibration input to the deployment
    semantics (FEAT_SAT) before the forward pass.
    """
    stats = {name: [float("inf"), float("-inf")] for name, _ in RELU_HOOK_LAYERS}
    stats["fc2"] = [float("inf"), float("-inf")]
    stats["dom_fc2"] = [float("inf"), float("-inf")]
    batch_max_trace = {name: [] for name in stats}
    observers = {name: MaxObserver() for name in histogram_layers}

    hooks = []
    for layer_name, module_name in RELU_HOOK_LAYERS:
        def mk_hook(stat_key):
            def hook(_mod, _inp, out):
                o = out.detach()
                stats[stat_key][0] = min(stats[stat_key][0], float(o.min()))
                stats[stat_key][1] = max(stats[stat_key][1], float(o.max()))
                batch_max_trace[stat_key].append(float(o.max()))
                if stat_key in observers:
                    observers[stat_key].update(o.cpu().numpy().ravel())
            return hook
        hooks.append(getattr(model, module_name).register_forward_hook(
            mk_hook(layer_name)))

    with torch.no_grad():
        for i in range(0, len(calib_rows), batch):
            rows = calib_rows[i:i + batch]
            x = torch.from_numpy(np.asarray(feats_m[rows], dtype=np.float32)
                                 )[:, None, :, :]
            if feat_clip is not None:
                x = torch.clamp(x, feat_clip[0], feat_clip[1])
            act_logits, dom_logits = model.forward_dual(x)
            for key, out in (("fc2", act_logits), ("dom_fc2", dom_logits)):
                o = out.detach()
                stats[key][0] = min(stats[key][0], float(o.min()))
                stats[key][1] = max(stats[key][1], float(o.max()))
                batch_max_trace[key].append(float(o.max()))
    for h in hooks:
        h.remove()
    return {"stats": stats, "batch_max_trace": batch_max_trace,
            "observers": observers}


# ---------------------------------------------------------------------------
# Weight image assembly (8-class layout, 8 layers).
# ---------------------------------------------------------------------------
def build_image(layer_params: dict) -> tuple:
    """Assemble the IRW1 weight image bytes and per-layer layout records.

    layer_params[name] needs: weight_int8 (Cout,K), bias_int32, m, shift,
    s_in/zp_in/s_out/zp_out, weight_shape, in/out shapes, layer_type.
    """
    segments = []
    layer_records = []
    offset = FIRST_LAYER_OFFSET

    for layer_id, (name, layer_type, weight_shape, in_shape, out_shape) in \
            enumerate(LAYER_SPECS):
        p = layer_params[name]
        weight = p["weight_int8"]
        cout = weight_shape[0]
        if layer_type == "conv":
            cin = weight_shape[1]
            weight_k = cin * 9
            in_shape_padded = in_shape
            out_shape_padded = out_shape
        else:
            cin = weight_shape[1]
            weight_k = cin
            in_shape_padded = (in_shape[0], 1, 1)
            out_shape_padded = (out_shape[0], 1, 1)
        assert weight.shape == (cout, weight_k), (name, weight.shape)

        weight_2d = weight.reshape(cout, weight_k)
        interleaved = interleave_group_major(weight_2d)
        weight_bytes = interleaved.tobytes()

        bias_bytes = p["bias_int32"].astype(np.int32).tobytes()
        m_bytes = p["m"].astype(np.int32).tobytes()
        shift_bytes = p["shift"].astype(np.uint8).tobytes()

        bias_off = len(weight_bytes)
        m_off = bias_off + len(bias_bytes)
        shift_off = m_off + len(m_bytes)
        segment_bytes = shift_off + len(shift_bytes)
        padded_len = (segment_bytes + ALIGN_BYTES - 1) // ALIGN_BYTES * ALIGN_BYTES

        wsum = weight_2d.sum(axis=1).astype(np.int32)
        num_groups = (cout + GROUP_CHANNELS - 1) // GROUP_CHANNELS

        layer_records.append({
            "name": name, "layer_id": layer_id, "layer_type": layer_type,
            "s_in": p["s_in"], "zp_in": p["zp_in"],
            "s_out": p["s_out"], "zp_out": p["zp_out"],
            "activation_dtype": "torch.quint8",
            "m": p["m"].tolist(), "shift": p["shift"].tolist(),
            "m_min": int(p["m"].min()), "m_max": int(p["m"].max()),
            "shift_min": int(p["shift"].min()), "shift_max": int(p["shift"].max()),
            "weight_scale_min": float(p["s_w"].min()),
            "weight_scale_max": float(p["s_w"].max()),
            "num_groups": num_groups, "num_channels": cout,
            "group_channels": GROUP_CHANNELS,
            "last_group_channels": cout - (num_groups - 1) * GROUP_CHANNELS,
            "weight_k": weight_k, "weight_shape": list(weight_shape),
            "in_shape": list(in_shape), "out_shape": list(out_shape),
            "in_shape_padded": list(in_shape_padded),
            "out_shape_padded": list(out_shape_padded),
            "weight_bytes": len(weight_bytes), "bias_bytes": len(bias_bytes),
            "m_bytes": len(m_bytes), "shift_bytes": len(shift_bytes),
            "segment_bytes": segment_bytes, "image_offset": offset,
            "ddr3_offset": DDR3_WEIGHT_BASE + offset,
            "bias_off": bias_off, "m_off": m_off, "shift_off": shift_off,
            "bias_int32": p["bias_int32"].tolist(),
            "bias_source": p["bias_source"],
            "padding_value": p["zp_in"],
            "zp_in_correction": {
                "enabled": p["zp_in"] != 0, "zp_in": p["zp_in"],
                "wsum": wsum.tolist(),
            },
        })
        segments.append((name, weight_bytes + bias_bytes + m_bytes
                         + shift_bytes, padded_len))
        offset += padded_len

    contract_table = b"".join(pack_contract_entry(rec) for rec in layer_records)
    assert len(contract_table) == NUM_LAYERS * CONTRACT_ENTRY_BYTES

    payload = bytearray(contract_table)
    gap = FIRST_LAYER_OFFSET - CONTRACT_TABLE_OFFSET - len(contract_table)
    assert gap >= 0
    payload += b"\x00" * gap
    for _, content, padded_len in segments:
        payload += content
        payload += b"\x00" * (padded_len - len(content))
    payload = bytes(payload)
    total_bytes = HEADER_BYTES + len(payload)
    checksum = segment_checksum_128(payload)
    header = struct.pack("<4sHHII16s", IMAGE_MAGIC, NUM_LAYERS, FORMAT_VERSION,
                         total_bytes, len(payload), checksum)
    image = header + payload
    assert len(image) == total_bytes

    layout = {
        "header_offset": 0, "header_bytes": HEADER_BYTES,
        "contract_table_offset": CONTRACT_TABLE_OFFSET,
        "contract_table_bytes": NUM_LAYERS * CONTRACT_ENTRY_BYTES,
        "first_layer_offset": FIRST_LAYER_OFFSET,
        "total_bytes": total_bytes, "payload_bytes": len(payload),
        "payload_checksum_128": checksum.hex(),
        "regions": [{"name": rec["name"], "offset": rec["image_offset"],
                     "bytes": rec["segment_bytes"]} for rec in layer_records],
    }
    return image, layer_records, layout


def load_weights_from_image(contract: dict, image_path: Path) -> dict:
    """Read per-layer weight/bias/M/shift blocks back from the image.

    Mirrors the RTL weight-stream consumption order and doubles as a parse
    check of the group5 image layout (offsets from the contract, contents
    cross-checked against the recorded arrays).
    """
    image = np.fromfile(str(image_path), dtype=np.uint8)
    assert image.size == contract["image_total_bytes"], (
        f"image size {image.size} != contract {contract['image_total_bytes']}")
    layers = {}
    for rec in contract["layers"]:
        base = rec["image_offset"]
        seg = image[base:base + rec["segment_bytes"]]
        w_blk = np.frombuffer(
            seg[:rec["weight_bytes"]].tobytes(), dtype=np.int8)
        weight = _deinterleave_group_major(
            w_blk, rec["num_channels"], rec["weight_k"])
        bias = np.frombuffer(
            seg[rec["bias_off"]:rec["bias_off"] + rec["bias_bytes"]]
            .tobytes(), dtype=np.int32).astype(np.int64)
        m_arr = np.frombuffer(
            seg[rec["m_off"]:rec["m_off"] + rec["m_bytes"]]
            .tobytes(), dtype=np.int32).astype(np.int64)
        shift = np.frombuffer(
            seg[rec["shift_off"]:rec["shift_off"] + rec["shift_bytes"]]
            .tobytes(), dtype=np.uint8).astype(np.int64)
        assert bias.tolist() == rec["bias_int32"], rec["name"]
        assert m_arr.tolist() == rec["M"], rec["name"]
        assert shift.tolist() == rec["shift"], rec["name"]
        layers[rec["name"]] = {
            "rec": rec, "weight": weight, "bias": bias,
            "m": m_arr, "shift": shift,
            "weight_f64": weight.astype(np.float64),
        }
    return layers


# ---------------------------------------------------------------------------
# Bit-exact INT8 forward (batched, float64 BLAS MAC + rint integer recovery).
# ---------------------------------------------------------------------------
def quantize_input_feat(x_f32: np.ndarray, inv_s_in: int, zp_in: int) -> np.ndarray:
    """Integer inv_s_in Q8.24 path: sat_u8(RHE(x*inv_s_in >> 24) + zp_in)."""
    x64 = rhe_float(x_f32.astype(np.float64) * np.int64(inv_s_in))
    q = round_half_even_shift(x64.astype(np.int64), QUANT_IN_FRAC_BITS)
    q = q + np.int64(zp_in)
    return np.clip(q, 0, 255).astype(np.uint8)


def requant_u8(acc_i64: np.ndarray, m: np.ndarray, shift: np.ndarray,
               zp_out: int) -> np.ndarray:
    """sat_u8(RHE(acc*M >>> shift) + zp_out) -- 8-class R-C RHE contract.

    The per-channel parameter axis is always the LAST axis of acc
    ((R, Cout) or (Cout,)).
    """
    chan = (1,) * (acc_i64.ndim - 1) + (m.size,)
    prod = acc_i64 * m.reshape(chan)
    y = round_half_even_shift(prod, shift.reshape(chan)) + np.int64(zp_out)
    return np.clip(y, 0, 255).astype(np.uint8)


def conv2d_int8_batch(x_u8: np.ndarray, blk: dict) -> np.ndarray:
    """3x3 stride-1 pad-1 INT8 conv on uint8 maps (N, Cin, H, W).

    Zero padding in the SIGNED domain (x - zp_in); float64 BLAS matmul with
    rint() integer recovery (see module docstring exactness proof); requant
    per the RHE contract.
    """
    rec = blk["rec"]
    n, cin, h, w = x_u8.shape
    cout = rec["num_channels"]
    k = rec["weight_k"]
    assert k == cin * 9, (rec["name"], k, cin)
    zp_in = rec["zp_in"]
    padded = np.zeros((n, cin, h + 2, w + 2), dtype=np.float64)
    padded[:, :, 1:-1, 1:-1] = x_u8.astype(np.float64) - np.float64(zp_in)
    win = np.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(2, 3))
    win = win.transpose(0, 2, 3, 1, 4, 5).reshape(n * h * w, cin * 9)
    acc = win @ blk["weight_f64"].T
    acc_i64 = rhe_float(acc).astype(np.int64)
    acc_i64 = acc_i64 + blk["bias"][None, :]
    out = requant_u8(acc_i64, blk["m"], blk["shift"], rec["zp_out"])
    # (n*h*w, cout) -> (n, cout, h, w): position-major rows need an explicit
    # transpose AFTER the reshape (a bare reshape would scramble the
    # channel/position axes).
    return np.ascontiguousarray(
        out.reshape(n, h, w, cout).transpose(0, 3, 1, 2))


def conv2d_int8_int64_ref(x_u8: np.ndarray, blk: dict) -> np.ndarray:
    """Pure int64 reference conv (single sample, exactness cross-check)."""
    rec = blk["rec"]
    cin, h, w = x_u8.shape
    cout = rec["num_channels"]
    zp_in = rec["zp_in"]
    padded = np.zeros((cin, h + 2, w + 2), dtype=np.int64)
    padded[:, 1:-1, 1:-1] = x_u8.astype(np.int64) - np.int64(zp_in)
    win = np.lib.stride_tricks.sliding_window_view(padded, (3, 3), axis=(1, 2))
    win2 = win.reshape(cin, h, w, 9).transpose(1, 2, 0, 3).reshape(h * w, cin * 9)
    wk = blk["weight"].reshape(cout, cin, 9)
    acc = np.tensordot(win2, wk.reshape(cout, cin * 9), axes=([1], [1]))
    acc = acc + blk["bias"][None, :]
    out = requant_u8(acc, blk["m"], blk["shift"], rec["zp_out"])
    return out.reshape(h, w, cout).transpose(2, 0, 1)


def maxpool2x2_batch(x_u8: np.ndarray) -> np.ndarray:
    """2x2 stride-2 max pool, floor geometry (odd tail dropped)."""
    n, c, h, w = x_u8.shape
    oh, ow = h // 2, w // 2
    view = x_u8[:, :, :oh * 2, :ow * 2].reshape(n, c, oh, 2, ow, 2)
    return view.max(axis=(3, 5))


def gap_batch(x_u8: np.ndarray) -> np.ndarray:
    """GAP over the 4x8 map: RHE(per-channel s32 sum >> 5).

    Identity quantization: the output lives in the conv4 output domain
    (same scale/zp), matching the 8-class GAP contract at 32 taps.
    """
    total = x_u8.astype(np.int64).sum(axis=(2, 3))
    return round_half_even_shift(total, GAP_SHIFT)


def fc_int8_batch(x_vec: np.ndarray, blk: dict) -> np.ndarray:
    """FC INT8 layer on integer container vectors (N, Cin).

    MACs on (x - zp_in) * w with the rebuilt int32 bias; requant per the
    RHE contract.  For fc1/dom_fc1 (zp_out == 0) the quint8 lower rail
    realizes the ReLU clamp.
    """
    rec = blk["rec"]
    x_eff = x_vec.astype(np.float64) - np.float64(rec["zp_in"])
    acc = x_eff @ blk["weight_f64"].T
    acc_i64 = rhe_float(acc).astype(np.int64) + blk["bias"][None, :]
    return requant_u8(acc_i64, blk["m"], blk["shift"], rec["zp_out"])


def npu_forward_group5(feat_f32: np.ndarray, contract: dict, weights: dict,
                       keep_layers: bool = False) -> dict:
    """Full INT8 forward: (N,1,64,130) float feats -> dual-head logits.

    Returns float-domain logits (out - zp_out) * s_out for both heads plus
    (optionally) every intermediate uint8 stage.
    """
    qs = contract["quant_stub_input_contract"]
    feat_u8 = quantize_input_feat(feat_f32[:, 0, :, :],
                                  int(qs["inv_s_in"]), int(qs["zp_in"]))
    x = feat_u8[:, None, :, :]                       # (N,1,64,130)
    c1 = conv2d_int8_batch(x, weights["conv1"])
    p1 = maxpool2x2_batch(c1)
    c2 = conv2d_int8_batch(p1, weights["conv2"])
    p2 = maxpool2x2_batch(c2)
    c3 = conv2d_int8_batch(p2, weights["conv3"])
    p3 = maxpool2x2_batch(c3)
    c4 = conv2d_int8_batch(p3, weights["conv4"])
    p4 = maxpool2x2_batch(c4)
    gap = gap_batch(p4)                              # (N,256) int64
    f1 = fc_int8_batch(gap, weights["fc1"])          # (N,128) u8 ReLU rail
    act_u8 = fc_int8_batch(f1, weights["fc2"])       # (N,5) u8 logits
    d1 = fc_int8_batch(gap, weights["dom_fc1"])      # (N,128) u8 ReLU rail
    dom_u8 = fc_int8_batch(d1, weights["dom_fc2"])   # (N,5) u8 logits

    def deq(u8, layer_name):
        rec = {r["name"]: r for r in contract["layers"]}[layer_name]
        return (u8.astype(np.float64) - rec["zp_out"]) * rec["s_out"]

    out = {
        "act_logits": deq(act_u8, "fc2"),
        "dom_logits": deq(dom_u8, "dom_fc2"),
        "act_logits_container": act_u8.astype(np.int64)
        - np.int64({r["name"]: r for r in contract["layers"]}["fc2"]["zp_out"]),
        "dom_logits_container": dom_u8.astype(np.int64)
        - np.int64({r["name"]: r for r in contract["layers"]}["dom_fc2"]["zp_out"]),
    }
    if keep_layers:
        out.update({
            "feat_u8": feat_u8, "conv1": c1, "pool1": p1, "conv2": c2,
            "pool2": p2, "conv3": c3, "pool3": p3, "conv4": c4, "pool4": p4,
            "gap": gap, "fc1": f1, "fc2": act_u8,
            "dom_fc1": d1, "dom_fc2": dom_u8,
        })
    return out


def int64_crosscheck(feat_f32: np.ndarray, contract: dict, weights: dict) -> dict:
    """Verify float64-BLAS + rint == pure int64 MAC on real samples."""
    feat_u8 = quantize_input_feat(
        feat_f32[:, 0, :, :],
        int(contract["quant_stub_input_contract"]["inv_s_in"]),
        int(contract["quant_stub_input_contract"]["zp_in"]))
    res = {}
    x = feat_u8[:, None, :, :]
    c1 = conv2d_int8_batch(x, weights["conv1"])
    ref1 = conv2d_int8_int64_ref(feat_u8[0][None, :, :], weights["conv1"])
    res["conv1"] = int(np.abs(c1[0].astype(np.int64) - ref1.astype(np.int64)).max())
    p1 = maxpool2x2_batch(c1)
    c2 = conv2d_int8_batch(p1, weights["conv2"])
    ref2 = conv2d_int8_int64_ref(p1[0], weights["conv2"])
    res["conv2"] = int(np.abs(c2[0].astype(np.int64) - ref2.astype(np.int64)).max())
    p2 = maxpool2x2_batch(c2)
    c3 = conv2d_int8_batch(p2, weights["conv3"])
    ref3 = conv2d_int8_int64_ref(p2[0], weights["conv3"])
    res["conv3"] = int(np.abs(c3[0].astype(np.int64) - ref3.astype(np.int64)).max())
    p3 = maxpool2x2_batch(c3)
    c4 = conv2d_int8_batch(p3, weights["conv4"])
    ref4 = conv2d_int8_int64_ref(p3[0], weights["conv4"])
    res["conv4"] = int(np.abs(c4[0].astype(np.int64) - ref4.astype(np.int64)).max())
    return res


# ---------------------------------------------------------------------------
# Main pipeline: calibrate -> contract -> image -> deploy npy -> self checks.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Group5 INT8 quantization contract generator.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS_DIR)
    parser.add_argument("--calib-n", type=int, default=8000,
                        help="stratified train rows for activation calibration")
    parser.add_argument("--seed", type=int, default=20261102)
    parser.add_argument("--batch", type=int, default=256)
    parser.add_argument("--out-domain", choices=("minmax", "sat"),
                        default="sat",
                        help="output-head calibration domain: minmax (raw "
                             "observed range) or sat (semantic saturation "
                             "clip, default: fc2 +/-14 sigmoid bound, "
                             "dom_fc2 24-wide softmax span)")
    parser.add_argument("--interior-pct", type=float, default=99.99,
                        help="element percentile used as the calibration max "
                             "of conv1..conv4 (ReLU long tails inflate the "
                             "raw max 5..6x); 0 disables (plain MinMax). "
                             "Defaults to the accepted round-2 variant: "
                             "p99.99 + feat-sat 6.5 reaches 0.971 dominant "
                             "agreement / -0.0075 macro F1; p99.9 measured "
                             "-0.042 macro F1 and plain MinMax only 0.967 "
                             "agreement (see reports/group5_int8_calibration"
                             "_20261103.json)")
    parser.add_argument("--feat-sat", type=float, default=6.5,
                        help="input z-domain saturation bound used for the "
                             "calibration domain (8.0 = the 8-class Q4.12 "
                             "sat16 precedent; val elements beyond +6.5 are "
                             "< 2e-5).  Defaults to the accepted round-2 "
                             "variant")
    args = parser.parse_args(argv)

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    contract_path = outdir / "group5_contract.json"
    image_path = outdir / "group5_weights_image.bin"

    # ---- load assets ------------------------------------------------------
    model, state, bn_eps = load_float_model(args.model_dir)
    with open(args.model_dir / "manifest.json", "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["group_order"] == GROUP_NAMES
    assert manifest["checkpoint_epoch"] == 22

    with open(args.cache_dir / "split.json", "r", encoding="utf-8") as fh:
        split = json.load(fh)
    train_idx = np.asarray(split["train_indices"], dtype=np.int64)
    val_idx = np.asarray(split["val_indices"], dtype=np.int64)
    feats_m = np.load(args.cache_dir / "all_features.npy", mmap_mode="r")
    labels_all = np.load(args.cache_dir / "labels.npy")

    float_state_sha = sha256_file(args.model_dir / "float_state.npz")
    ref_vec_sha = sha256_file(args.model_dir / "reference_vectors.npz")
    feats_sha = sha256_file(args.cache_dir / "all_features.npy")

    # ---- BN fold + weight quantization ------------------------------------
    folded = bn_fold(state, bn_eps)
    weight_q = {}
    for name, _, wshape, _, _ in LAYER_SPECS:
        w2d = folded[name]["w"].reshape(wshape[0], -1)
        q, s_w = quantize_weight_symmetric(w2d)
        weight_q[name] = {"weight_int8": q, "s_w": s_w}

    # ---- calibration ------------------------------------------------------
    print(f"[calib] stratified sample of {args.calib_n} train rows "
          f"(seed {args.seed}, all percussion rows kept)")
    calib_rows = stratified_sample(labels_all[train_idx], args.calib_n,
                                   args.seed)
    print(f"[calib] selected {len(calib_rows)} rows "
          f"(percussion positives: {int((labels_all[train_idx][calib_rows][:, 3] > .5).sum())})")

    print("[calib] full train-split feature min/max scan ...")
    feat_min, feat_max = full_feature_minmax(feats_m, train_idx)
    print(f"[calib] input feat range [{feat_min:.4f}, {feat_max:.4f}]")
    feat_sat = float(args.feat_sat)
    feat_min = max(feat_min, -feat_sat)
    feat_max = min(feat_max, feat_sat)
    print(f"[calib] input feat calibration domain after +/-{feat_sat:g} "
          f"saturation clip: [{feat_min:.4f}, {feat_max:.4f}]")

    print("[calib] forward hooks over calibration rows ...")
    hist_layers = () if args.interior_pct <= 0 else (
        "conv1", "conv2", "conv3", "conv4")
    calib = calibrate_activations(model, feats_m, train_idx[calib_rows],
                                  batch=args.batch,
                                  histogram_layers=hist_layers,
                                  feat_clip=(-feat_sat, feat_sat))
    stats = calib["stats"]
    pct_max = {}
    if hist_layers:
        for name in hist_layers:
            pct_max[name] = calib["observers"][name].percentile_max(
                args.interior_pct)
            print(f"[calib] {name:8s} p{args.interior_pct:g} max "
                  f"{pct_max[name]:.4f} (raw {stats[name][1]:.4f})")
    for name in ("conv1", "conv2", "conv3", "conv4", "fc1", "fc2",
                 "dom_fc1", "dom_fc2"):
        print(f"[calib] {name:8s} obs [{stats[name][0]:+.4f}, "
              f"{stats[name][1]:+.4f}]")

    # ---- per-layer quantization parameters --------------------------------
    # Layer input domains: conv1 <- input feat; conv{i+1} <- conv{i} output;
    # fc1/dom_fc1 <- conv4 output (GAP identity); fc2 <- fc1; dom_fc2 <- dom_fc1.
    s_in_map = {"conv1": None}
    layer_params = {}
    quant_records = {}
    for name, _, wshape, in_shape, _ in LAYER_SPECS:
        if name == "conv1":
            s_in, zp_in = qparams_from_minmax(feat_min, feat_max)
        else:
            if name == "conv2":
                src = "conv1"
            elif name == "conv3":
                src = "conv2"
            elif name == "conv4":
                src = "conv3"
            elif name in ("fc1", "dom_fc1"):
                src = "conv4"
            elif name == "fc2":
                src = "fc1"
            elif name == "dom_fc2":
                src = "dom_fc1"
            s_in, zp_in = layer_params[src]["s_out"], layer_params[src]["zp_out"]
        s_out, zp_out = qparams_from_minmax(*stats[name])
        if args.interior_pct > 0 and name in hist_layers:
            # percentile-trimmed interior max (clip semantics: the u8
            # saturation realizes the clip, monotonous for maxpool/conv)
            s_out, zp_out = qparams_from_minmax(
                stats[name][0], pct_max[name])
        if args.out_domain == "sat":
            if name == "fc2":
                s_out, zp_out = qparams_from_minmax(
                    stats[name][0], stats[name][1],
                    clip_lo=-ACT_SAT_LOGIT, clip_hi=ACT_SAT_LOGIT)
            elif name == "dom_fc2":
                obs_max = max(stats[name][1], 0.0)
                s_out, zp_out = qparams_from_minmax(
                    stats[name][0], stats[name][1],
                    clip_lo=obs_max - DOM_SPAN, clip_hi=obs_max)

        wq = weight_q[name]
        ratio = wq["s_w"] * (s_in / s_out)
        m_list, shift_list = [], []
        for r in ratio:
            m_c, s_c = compute_m_shift(float(r))
            m_list.append(m_c)
            shift_list.append(s_c)
        m_arr = np.asarray(m_list, dtype=np.int64)
        shift_arr = np.asarray(shift_list, dtype=np.int64)

        # bias rebuilt from the float state (BN-folded), never npy astype.
        denom = s_in * wq["s_w"]
        bias_int32 = rhe_float(folded[name]["b"] / denom).astype(np.int64)
        assert np.all(np.abs(bias_int32) < (1 << 31)), name
        bias_source = ("float_state_bn_fold_rhe(b/(s_in*s_w))" if name.startswith("conv")
                       else "float_state_linear_bias_rhe(b/(s_in*s_w))")

        layer_params[name] = {
            "weight_int8": wq["weight_int8"], "s_w": wq["s_w"],
            "bias_int32": bias_int32, "m": m_arr, "shift": shift_arr,
            "s_in": s_in, "zp_in": int(zp_in),
            "s_out": s_out, "zp_out": int(zp_out),
            "bias_source": bias_source,
        }
        quant_records[name] = {
            "observed_min": stats[name][0], "observed_max": stats[name][1],
            "calibration_max": (pct_max[name] if name in pct_max
                                else stats[name][1]),
            "interior_percentile": (args.interior_pct if name in pct_max
                                    else None),
            "s_in": s_in, "zp_in": int(zp_in),
            "s_out": s_out, "zp_out": int(zp_out),
            "weight_scale_min": float(wq["s_w"].min()),
            "weight_scale_max": float(wq["s_w"].max()),
            "batch_max_trace": calib["batch_max_trace"][name],
        }
        print(f"[quant] {name:8s} s_in={s_in:.6g} zp_in={zp_in:3d} "
              f"s_out={s_out:.6g} zp_out={zp_out:3d} "
              f"shift[{shift_arr.min()},{shift_arr.max()}]")

    # ---- weight image ------------------------------------------------------
    image_bytes, layer_records, layout = build_image(layer_params)
    image_path.write_bytes(image_bytes)
    image_sha = sha256_file(image_path)
    print(f"[image] wrote {image_path} ({len(image_bytes)} bytes, "
          f"sha256 {image_sha[:16]}...)")

    # ---- contract JSON -----------------------------------------------------
    inv = choose_inv_s_in(layer_params["conv1"]["s_in"])
    contract = {
        "generator": GENERATOR_NAME,
        "spec_refs": SPEC_REFS,
        "format_version": 1,
        "image_magic": IMAGE_MAGIC.decode("ascii"),
        "image_sha256": image_sha,
        "image_total_bytes": layout["total_bytes"],
        "payload_checksum_128": layout["payload_checksum_128"],
        "model_id": {
            "name": "group5_v3_float_20261102",
            "checkpoint_epoch": manifest["checkpoint_epoch"],
            "model_class": "DualHeadInstrumentCNN",
            "num_classes": 5,
            "input_shape": [1, 1, 64, 130],
            "float_state_sha256": float_state_sha,
            "reference_vectors_sha256": ref_vec_sha,
            "source_checkpoint_sha256": manifest["source_checkpoint_sha256"],
        },
        "dual_head": {
            "activity": "fc1(256->128)+ReLU+fc2(128->5), sigmoid per class",
            "dominance": "dom_fc1(256->128)+ReLU+dom_fc2(128->5), softmax; "
                         "post-process masks by activity>0.5 and renormalizes",
            "hw_reuse": "both heads serialize over the same NPU fc engine; "
                        "weight image segments are separate (activity first)",
        },
        "ddr3_weight_base": DDR3_WEIGHT_BASE,
        "ddr3_weight_base_hex": f"0x{DDR3_WEIGHT_BASE:08X}",
        "ddr3_note": "planned base, disjoint from the 8-class image "
                     "(0x00100000..0x001A8DE0); final map set by weight_loader",
        "determinism": "byte-identical on re-run: fixed stratified-sample "
                       "seed, pure integer packing, json floats round-trip",
        "requant_formula": (
            "y = sat_u8(round_half_even(acc_s32 * M[c] >>> shift[c]) + zp_out); "
            "M[c] = round(s_w[c] * s_in / s_out * 2^shift[c]), "
            "M[c] in [2^30, 2^31) (Q0.31)"
        ),
        "requant_rounding_note": (
            "round-half-even is mandatory (8-class R-C lesson: truncating "
            "shifts accumulate a half-LSB bias amplified to +/-32 LSB/layer "
            "through 432-tap convolutions)"
        ),
        "activation_dtype_note": (
            "all activations are quint8 (unsigned 8-bit); conv1 input zp_in "
            "is a POSITIVE offset, requiring the -zp_in*sum(w) accumulator "
            "correction (zp_in_correction.wsum) AND zero-padding with "
            "padding_value == zp_in, not 0"
        ),
        "bias_note": (
            "bias_int32 rebuilt exactly from float_state.npz "
            "(BN-folded float bias, round-half-even by 1/(s_in*s_w[c])); "
            "the 8-class astype(np.int32) corruption is not repeated here"
        ),
        "gap_contract": {
            "geometry": list(GAP_GEOMETRY),
            "taps": GAP_GEOMETRY[0] * GAP_GEOMETRY[1],
            "shift": GAP_SHIFT,
            "rounding": "round_half_even",
            "quantization": "identity (fc1/dom_fc1 input domain == conv4 "
                            "output domain)",
            "note": "5-class pool4 map is 4x8=32 taps (8-class was 8x16=64 "
                    "with >>6); requant shift is 5, not 6",
        },
        "quant_stub_input_contract": {
            "description": (
                "float z-domain feature -> quint8: x_u8 = sat_u8("
                "RHE(x * inv_s_in >> 24) + zp_in), inv_s_in in Q8.24; the "
                "u8 saturation realizes the +/-8 z-domain clip"),
            "s_in": layer_params["conv1"]["s_in"],
            "zp_in": layer_params["conv1"]["zp_in"],
            "dtype": "torch.quint8",
            "inv_s_in": inv["value"],
            "inv_s_in_format": inv["format"],
            "inv_s_in_bits": inv["bits"],
            "feat_saturation": float(args.feat_sat),
            "note": "calibrated on the FULL train split min/max of "
                    "all_features.npy (float z-domain) saturated to +/-8 "
                    "(8-class fixed-point z container Q4.12 sat16 precedent; "
                    "val-set elements beyond +8 are < 1e-5, semantically "
                    "free to clip). The fixed-point z-container format of "
                    "the future 5-class mel pipeline should adopt the same "
                    "+/-8 saturation",
        },
        "classes": {
            "num_classes": 5,
            "names": GROUP_NAMES,
            "names_zh": GROUP_NAMES_ZH,
            "asserted_against": "models/group5_v3_float_20261102/manifest.json "
                                "group_order + cache metadata.json group_names",
            "head_layout": {"activity": "fc2 rows 0..4",
                            "dominance": "dom_fc2 rows 0..4 (same order)"},
        },
        "calibration": {
            "method": (
                "minmax + semantic saturation clip on the output heads "
                "(fc2: +/-14 sigmoid bound, dom_fc2: 24-wide softmax span "
                "anchored at the observed max; lossless for prediction "
                "semantics, monotone clip preserves argmax); interior "
                "layers plain minmax (fbgemm observer parity, 0 kept "
                "representable)"
            ) if args.out_domain == "sat" else
            "minmax (fbgemm observer parity: 0 kept representable)",
            "out_domain_variant": args.out_domain,
            "train_rows_total": int(len(train_idx)),
            "calib_rows_used": int(len(calib_rows)),
            "stratification": "5-bit activity label signature, proportional; "
                              "all percussion-positive train rows kept",
            "seed": args.seed,
            "input_stats_source": "full train split min/max over "
                                  "all_features.npy",
            "input_observed_min": feat_min,
            "input_observed_max": feat_max,
            "features_sha256": feats_sha,
            "layer_stats": quant_records,
        },
        "layers": [
            {
                "name": rec["name"], "layer_id": rec["layer_id"],
                "layer_type": rec["layer_type"],
                "s_in": rec["s_in"], "s_out": rec["s_out"],
                "zp_in": rec["zp_in"], "zp_out": rec["zp_out"],
                "activation_dtype": rec["activation_dtype"],
                "M": rec["m"], "shift": rec["shift"],
                "M_min": rec["m_min"], "M_max": rec["m_max"],
                "shift_min": rec["shift_min"], "shift_max": rec["shift_max"],
                "weight_scale_min": rec["weight_scale_min"],
                "weight_scale_max": rec["weight_scale_max"],
                "num_groups": rec["num_groups"],
                "num_channels": rec["num_channels"],
                "group_channels": rec["group_channels"],
                "last_group_channels": rec["last_group_channels"],
                "weight_k": rec["weight_k"],
                "weight_shape": rec["weight_shape"],
                "in_shape": rec["in_shape"], "out_shape": rec["out_shape"],
                "weight_bytes": rec["weight_bytes"],
                "bias_bytes": rec["bias_bytes"],
                "m_bytes": rec["m_bytes"], "shift_bytes": rec["shift_bytes"],
                "segment_bytes": rec["segment_bytes"],
                "image_offset": rec["image_offset"],
                "ddr3_offset": rec["ddr3_offset"],
                "ddr3_offset_hex": f"0x{rec['ddr3_offset']:08X}",
                "bias_off": rec["bias_off"], "m_off": rec["m_off"],
                "shift_off": rec["shift_off"],
                "bias_int32": rec["bias_int32"],
                "bias_source": rec["bias_source"],
                "padding_value": rec["padding_value"],
                "zp_in_correction": rec["zp_in_correction"],
            }
            for rec in layer_records
        ],
        "image_layout": layout,
    }

    # ---- self checks (image round-trip, int64 exactness, reference) --------
    with open(contract_path, "w", encoding="utf-8") as fh:
        json.dump(contract, fh, indent=2)
        fh.write("\n")
    with open(contract_path, "r", encoding="utf-8") as fh:
        contract_rt = json.load(fh)      # round-trip parse check

    weights = load_weights_from_image(contract_rt, image_path)
    print("[check] weight image round-trip parse OK (bias/M/shift verified)")

    ref = np.load(args.model_dir / "reference_vectors.npz")
    ref_feat = np.asarray(ref["features"], dtype=np.float32)
    xcheck = int64_crosscheck(ref_feat[:1], contract_rt, weights)
    print(f"[check] float64-BLAS vs int64 MAC max LSB diff per conv layer: "
          f"{xcheck}")
    assert all(v == 0 for v in xcheck.values()), (
        "float64 BLAS + rint path is NOT integer-exact, aborting")

    sim = npu_forward_group5(ref_feat, contract_rt, weights)
    act_diff = np.abs(sim["act_logits"] - np.asarray(ref["activity_logits"]))
    dom_diff = np.abs(sim["dom_logits"] - np.asarray(ref["dominance_logits"]))
    # Saturated-clip semantics make raw logit deltas meaningless in the
    # saturation region; the probability-level deltas below are the health
    # signal (sigmoid probabilities and activity decisions).
    ref_act_prob = 1.0 / (1.0 + np.exp(-np.asarray(ref["activity_logits"],
                                                   dtype=np.float64)))
    sim_act_prob = 1.0 / (1.0 + np.exp(-sim["act_logits"]))
    act_prob_diff = np.abs(sim_act_prob - ref_act_prob)
    act_pred_agree = int(((sim_act_prob > 0.5) == (ref_act_prob > 0.5)).sum())
    exp_d = np.exp(sim["dom_logits"] - sim["dom_logits"].max(axis=1,
                                                             keepdims=True))
    sim_dom_prob = exp_d / exp_d.sum(axis=1, keepdims=True)
    ref_dom_l = np.asarray(ref["dominance_logits"], dtype=np.float64)
    exp_r = np.exp(ref_dom_l - ref_dom_l.max(axis=1, keepdims=True))
    ref_dom_prob = exp_r / exp_r.sum(axis=1, keepdims=True)
    dom_prob_diff = np.abs(sim_dom_prob - ref_dom_prob)
    ref_check = {
        "samples": int(ref_feat.shape[0]),
        "row_indices": np.asarray(ref["row_indices"]).tolist(),
        "max_abs_dlogit_activity": float(act_diff.max()),
        "max_abs_dlogit_dominance": float(dom_diff.max()),
        "note": "logit deltas include the lossless saturation clip "
                "(input +/-6.5, fc2 +/-14, dom_fc2 24-span); the "
                "probability-level deltas below are the health signal",
        "max_abs_dprob_activity": float(act_prob_diff.max()),
        "activity_decisions_matching": act_pred_agree,
        "activity_decisions_total": int(act_prob_diff.size),
        "max_abs_dprob_dominance": float(dom_prob_diff.max()),
        "activity_logits_int8": sim["act_logits"].round(6).tolist(),
        "dominance_logits_int8": sim["dom_logits"].round(6).tolist(),
    }
    contract_rt["reference_sample_check"] = ref_check
    with open(contract_path, "w", encoding="utf-8") as fh:
        json.dump(contract_rt, fh, indent=2)
        fh.write("\n")
    print(f"[check] 5 reference samples: max|dprob| activity "
          f"{ref_check['max_abs_dprob_activity']:.4f}, dominance "
          f"{ref_check['max_abs_dprob_dominance']:.4f}, activity decisions "
          f"{act_pred_agree}/{act_prob_diff.size} matching")

    # ---- deploy npy mirror -------------------------------------------------
    weights_dir: Path = args.weights_dir
    weights_dir.mkdir(parents=True, exist_ok=True)
    for name in layer_params:
        p = layer_params[name]
        np.save(weights_dir / f"{name}_weight_int8.npy",
                p["weight_int8"].astype(np.int8))
        np.save(weights_dir / f"{name}_weight_scale.npy", p["s_w"])
        np.save(weights_dir / f"{name}_bias_int32.npy",
                p["bias_int32"].astype(np.int32))
        np.save(weights_dir / f"{name}_M.npy", p["m"].astype(np.int32))
        np.save(weights_dir / f"{name}_shift.npy",
                p["shift"].astype(np.uint8))
    # round-trip integrity: the npy mirror must be bit-identical to the image
    for name in layer_params:
        b = np.load(weights_dir / f"{name}_bias_int32.npy")
        assert b.dtype == np.int32 and b.tolist() == layer_params[name]["bias_int32"].tolist()
        w = np.load(weights_dir / f"{name}_weight_int8.npy")
        assert w.dtype == np.int8 and np.array_equal(
            w, weights[name]["weight"].reshape(w.shape))
    def _rel(p: Path) -> str:
        try:
            return str(p.resolve().relative_to(PROJECT_DIR))
        except ValueError:
            return str(p.resolve())

    deploy_manifest = {
        "model_id": contract_rt["model_id"],
        "generator": GENERATOR_NAME,
        "contract_path": _rel(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "weights_image": _rel(image_path),
        "weights_image_sha256": image_sha,
        "layers": [
            {
                "name": name,
                "weight_int8": f"{name}_weight_int8.npy",
                "weight_scale": f"{name}_weight_scale.npy",
                "bias_int32": f"{name}_bias_int32.npy",
                "M": f"{name}_M.npy",
                "shift": f"{name}_shift.npy",
                "weight_shape": list(layer_params[name]["weight_int8"].shape),
            }
            for name in layer_params
        ],
        "integrity_note": "bias_int32 arrays are stored from the exact int64 "
                          "reconstruction (round-half-even), never from a "
                          "float astype cast",
    }
    with open(weights_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(deploy_manifest, fh, indent=2)
        fh.write("\n")
    print(f"[deploy] wrote npy weight mirror to {weights_dir}")

    print(json.dumps({
        "contract": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "image": str(image_path),
        "image_sha256": image_sha,
        "image_bytes": layout["total_bytes"],
        "reference_check": ref_check,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
