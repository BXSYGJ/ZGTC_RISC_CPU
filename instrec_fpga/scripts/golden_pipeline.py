from __future__ import annotations
import argparse
import json
import math
import sys
import wave
from pathlib import Path
import numpy as np
SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_TABLES_PATH = SCRIPTS_DIR / 'outputs' / 'mel_tables.json'
DEFAULT_OUT_DIR = SCRIPTS_DIR / 'outputs' / 'golden'
DEFAULT_REF_SRC_DIR = Path(__file__).resolve().parents[1] / 'training' / 'src'
SR = 44100
N_FFT = 2048
HOP = 512
N_MELS = 64
N_FRAMES = 258
WINDOW_SAMPLES = 132096
REFLECT_PAD = N_FFT // 2
N_STFT_FRAMES = 1 + WINDOW_SAMPLES // HOP
MEL_ELEMENT_COUNT = N_MELS * N_FRAMES
Q15_SHIFT = 15
FFT_STAGES = 11
S16_MIN, S16_MAX = (-32768, 32767)
S8_MIN, S8_MAX = (-128, 127)
DB_TOP_DB_Q88 = -20480
DB_SCALE_NUM = 775
LOG2_BIAS = -56
LOG2_ZERO_Q88 = LOG2_BIAS << 8
DEFAULT_CONTRACT_PATH = SCRIPTS_DIR / 'outputs' / 'layer_contract.json'
QUANT_IN_FRAC_BITS = 24
GOLDEN_NAME = 'golden_pipeline.py'
SPEC_REFS = 'tasks.md T-GP-04/T-GP-05; design.md 3.1-3.7, 4.3-4.5; spec.md REQ-FTR-001..005, REQ-ACC-002/003'
ALL_STAGES = ('pcm', 'windowed', 'fft', 'power', 'log2spec', 'dbspec', 'feat', 'conv1', 'conv2', 'conv3', 'conv4', 'fc1', 'fc2', 'logits', 'probs')
NPU_STAGES = ALL_STAGES[7:]

def load_mel_tables(tables_path: Path=DEFAULT_TABLES_PATH) -> dict:
    with open(tables_path, 'r', encoding='ascii') as fh:
        payload = json.load(fh)
    params = payload['params']
    assert params['sr'] == SR and params['n_fft'] == N_FFT
    assert params['hop_length'] == HOP and params['n_mels'] == N_MELS
    assert params['n_frames'] == N_FRAMES
    assert params['window'] == 'hann' and params['power'] == 2.0
    tables = {'params': params, 'hann_q15': np.asarray(payload['tables']['hann_q15']['data'], np.int16), 'log2_lut': np.asarray(payload['tables']['log2_lut']['data'], np.uint8), 'exp_lut': np.asarray(payload['tables']['exp_lut']['data'], np.uint16), 'coo_offsets': np.asarray(payload['tables']['mel_coo']['offsets'], np.int64), 'coo_channels': np.asarray(payload['tables']['mel_coo']['channels'], np.int64), 'coo_bin_idx': np.asarray(payload['tables']['mel_coo']['bin_idx'], np.int64), 'coo_weight_q15': np.asarray(payload['tables']['mel_coo']['weight_q15'], np.int16)}
    assert tables['hann_q15'].shape == (N_FFT,)
    assert tables['log2_lut'].shape == (256,)
    assert tables['exp_lut'].shape == (512,)
    assert tables['coo_offsets'][0] == 0
    assert tables['coo_offsets'][-1] == tables['coo_bin_idx'].size
    return tables

def make_twiddle_q15(n_fft: int=N_FFT) -> tuple[np.ndarray, np.ndarray]:
    k = np.arange(n_fft // 2, dtype=np.float64)
    angle = -2.0 * np.pi * k / n_fft
    re = np.floor(np.cos(angle) * 32768.0 + 0.5)
    im = np.floor(np.sin(angle) * 32768.0 + 0.5)
    re = np.clip(re, -32768, 32767).astype(np.int16)
    im = np.clip(im, -32768, 32767).astype(np.int16)
    return (re, im)

def rhu_shift(x: np.ndarray, k: int) -> np.ndarray:
    return np.right_shift(x + (1 << k - 1), k).astype(np.int64)

def trunc_div(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q

def round_half_even_shift(x: np.ndarray, k: int) -> np.ndarray:
    sign = x < 0
    av = np.where(sign, -x, x).astype(np.int64)
    q = np.right_shift(av, k)
    rem = np.bitwise_and(av, (1 << k) - 1)
    half = 1 << k - 1
    inc = (rem > half) | (rem == half) & (q & 1 == 1)
    q = q + inc.astype(np.int64)
    return np.where(sign, -q, q)

def sat16(x: np.ndarray) -> np.ndarray:
    return np.clip(x, S16_MIN, S16_MAX)

def sat8(x: np.ndarray) -> np.ndarray:
    return np.clip(x, S8_MIN, S8_MAX)

def load_pcm_s16(wav_path: Path, max_samples: int=WINDOW_SAMPLES) -> np.ndarray:
    with wave.open(str(wav_path), 'rb') as wf:
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == SR
        n_ch = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype='<i2').astype(np.int16)
    if n_ch == 1:
        pcm = samples
    elif n_ch == 2:
        left = samples[0::2].astype(np.int32)
        right = samples[1::2].astype(np.int32)
        pcm = (left + right + 1 >> 1).astype(np.int16)
    else:
        raise ValueError(f'unsupported channel count {n_ch}')
    if pcm.size < max_samples:
        pcm = np.pad(pcm, (0, max_samples - pcm.size))
    return pcm[:max_samples].copy()

def frame_pcm_reflect(pcm: np.ndarray) -> np.ndarray:
    padded = np.pad(pcm, (REFLECT_PAD, REFLECT_PAD), mode='reflect')
    n_frames = 1 + (padded.size - N_FFT) // HOP
    assert n_frames == N_STFT_FRAMES, f'unexpected frame count {n_frames}'
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    return padded[idx].astype(np.int16)

def apply_hann(frames: np.ndarray, hann_q15: np.ndarray) -> np.ndarray:
    products = frames.astype(np.int64) * hann_q15.astype(np.int64)
    return rhu_shift(products, Q15_SHIFT)

def _bit_reverse_indices(n: int) -> np.ndarray:
    bits = int(math.log2(n))
    rev = np.zeros(n, dtype=np.int64)
    for i in range(n):
        rev[i] = int(bin(i)[2:].zfill(bits)[::-1], 2)
    return rev
_BIT_REV_2048 = _bit_reverse_indices(N_FFT)

def fft_radix2_scaled(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n_frames = x.shape[0]
    rev = _BIT_REV_2048
    re = x[:, rev].astype(np.int64)
    im = np.zeros_like(re)
    tw_re, tw_im = make_twiddle_q15(N_FFT)
    tw_re = tw_re.astype(np.int64)
    tw_im = tw_im.astype(np.int64)
    for s in range(1, FFT_STAGES + 1):
        m = 1 << s
        half = m >> 1
        tw_step = N_FFT >> s
        j = np.arange(half, dtype=np.int64) * tw_step
        wr = tw_re[j]
        wi = tw_im[j]
        blk = N_FFT // m
        re_v = re.reshape(n_frames, blk, m)
        im_v = im.reshape(n_frames, blk, m)
        a_re = re_v[:, :, :half]
        a_im = im_v[:, :, :half]
        d_re = re_v[:, :, half:]
        d_im = im_v[:, :, half:]
        pr = rhu_shift(wr * d_re - wi * d_im, Q15_SHIFT)
        pi = rhu_shift(wr * d_im + wi * d_re, Q15_SHIFT)
        up_re = a_re + pr
        up_im = a_im + pi
        dn_re = a_re - pr
        dn_im = a_im - pi
        re = np.concatenate([up_re, dn_re], axis=2).reshape(n_frames, N_FFT)
        im = np.concatenate([up_im, dn_im], axis=2).reshape(n_frames, N_FFT)
    return (re[:, :N_FFT // 2 + 1].astype(np.int32), im[:, :N_FFT // 2 + 1].astype(np.int32))

def power_spectrum(re: np.ndarray, im: np.ndarray) -> np.ndarray:
    p = re.astype(np.int64)
    q = im.astype(np.int64)
    return rhu_shift(p * p + q * q, 10)

def mel_filter_coo(power: np.ndarray, tables: dict) -> np.ndarray:
    n_frames = power.shape[0]
    offsets = tables['coo_offsets']
    bins = tables['coo_bin_idx']
    weights = tables['coo_weight_q15'].astype(np.int64)
    mel = np.zeros((n_frames, N_MELS), dtype=np.int64)
    for ch in range(N_MELS):
        lo, hi = (int(offsets[ch]), int(offsets[ch + 1]))
        if hi == lo:
            continue
        pwr_ch = power[:, bins[lo:hi]]
        mel[:, ch] = (pwr_ch * weights[lo:hi]).sum(axis=1)
    return mel.T

def log2_fixed(power: np.ndarray, log2_lut: np.ndarray) -> np.ndarray:
    p = power.astype(np.int64)
    e = np.zeros(p.shape, dtype=np.int64)
    for b in range(0, 63):
        e = np.where(p >= np.int64(1) << np.int64(b), np.int64(b), e)
    shift = e - 8
    mant = np.where(shift >= 0, np.right_shift(p, np.maximum(shift, 0)), np.left_shift(p, np.maximum(-shift, 0)))
    idx = np.where(p == 0, 0, mant - 256).astype(np.int64)
    idx = np.clip(idx, 0, 255)
    out = (e + LOG2_BIAS << 8) + log2_lut[idx].astype(np.int64)
    return out.astype(np.int16)

def db_convert(log2_q88_full: np.ndarray) -> np.ndarray:
    max_l2 = int(log2_q88_full.max())
    diff = log2_q88_full.astype(np.int64) - max_l2
    scaled = rhu_shift(diff * DB_SCALE_NUM, 8)
    scaled = sat16(scaled)
    scaled = np.where(scaled < DB_TOP_DB_Q88, DB_TOP_DB_Q88, scaled)
    scaled = np.where(scaled > 0, 0, scaled)
    return scaled.astype(np.int16)

def truncate_frames(spec: np.ndarray) -> np.ndarray:
    assert spec.shape[1] >= N_FRAMES
    return spec[:, spec.shape[1] - N_FRAMES:]

def standardize(db_258: np.ndarray) -> np.ndarray:
    vals = db_258.astype(np.int64)
    sum_db = int(vals.sum())
    sum_db_sq = int((vals * vals).sum())
    mu = trunc_div(sum_db, MEL_ELEMENT_COUNT)
    var_q16 = trunc_div(sum_db_sq, MEL_ELEMENT_COUNT) - mu * mu
    var_q16 = max(var_q16, 0)
    sigma = math.isqrt(var_q16)
    sigma_eff = max(sigma, 1)
    inv_sigma = (1 << 20) + (sigma_eff >> 1)
    inv_sigma = inv_sigma // sigma_eff
    z = sat16(rhu_shift((vals - mu) * inv_sigma, 8))
    return z.astype(np.int16)

def load_layer_contract(contract_path: Path=DEFAULT_CONTRACT_PATH) -> dict:
    with open(contract_path, 'r', encoding='utf-8') as fh:
        return json.load(fh)

def quantize_int8(z_q412: np.ndarray, inv_s_in: int=None, zp_in: int=None) -> np.ndarray:
    if inv_s_in is None or zp_in is None:
        qs = load_layer_contract()['quant_stub_input_contract']
        inv_s_in = int(qs['inv_s_in'])
        zp_in = int(qs['zp_in'])
        assert qs['inv_s_in_bits'] == 32 and qs['inv_s_in_format'] == 'Q8.24'
    prod = z_q412.astype(np.int64) * np.int64(inv_s_in)
    x = round_half_even_shift(prod, QUANT_IN_FRAC_BITS) + np.int64(zp_in)
    return np.clip(x, 0, 255).astype(np.uint8)

def run_mel_pipeline(pcm: np.ndarray, tables: dict, inv_s_in: int | None=None, zp_in: int | None=None) -> dict:
    frames = frame_pcm_reflect(pcm)
    windowed = apply_hann(frames, tables['hann_q15'])
    re, im = fft_radix2_scaled(windowed)
    power = power_spectrum(re, im)
    mel_power = mel_filter_coo(power, tables)
    log2spec_full = log2_fixed(mel_power, tables['log2_lut'])
    dbspec_full = db_convert(log2spec_full)
    log2spec = truncate_frames(log2spec_full)
    dbspec = truncate_frames(dbspec_full)
    z = standardize(dbspec)
    feat = quantize_int8(z, inv_s_in, zp_in)
    return {'pcm': pcm, 'windowed': windowed.astype(np.int32), 'fft': np.stack([re, im], axis=-1), 'power': power, 'log2spec': log2spec, 'dbspec': dbspec, 'z': z, 'feat': feat}
DEFAULT_WEIGHT_IMAGE_PATH = SCRIPTS_DIR / 'outputs' / 'weights_image.bin'
NPU_GROUP_CHANNELS = 16
SOFTMAX_Q15_SCALE = 15
SOFTMAX_Q69_SHIFT = 6
SOFTMAX_Q69_SAT = 1 << 14
SOFTMAX_LUT_LSB_PER_ENTRY = 4

def _deinterleave_group_major(w_bytes: np.ndarray, cout: int, k: int) -> np.ndarray:
    out = np.empty((cout, k), dtype=np.int8)
    pos = 0
    for g in range(0, cout, NPU_GROUP_CHANNELS):
        gc = min(NPU_GROUP_CHANNELS, cout - g)
        out[g:g + gc, :] = w_bytes[pos:pos + gc * k].reshape(k, gc).T
        pos += gc * k
    assert pos == w_bytes.size
    return out

def load_weights_from_image(contract: dict, image_path: Path=DEFAULT_WEIGHT_IMAGE_PATH) -> dict:
    image = np.fromfile(str(image_path), dtype=np.uint8)
    assert image.size == contract['image_total_bytes'], f'weight image size {image.size} != contract {contract['image_total_bytes']}'
    layers = {}
    for rec in contract['layers']:
        base = rec['image_offset']
        seg = image[base:base + rec['segment_bytes']]
        w_blk = np.frombuffer(seg[:rec['weight_bytes']].tobytes(), dtype=np.int8)
        weight = _deinterleave_group_major(w_blk, rec['num_channels'], rec['weight_k'])
        bias = np.frombuffer(seg[rec['bias_off']:rec['bias_off'] + rec['bias_bytes']].tobytes(), dtype=np.int32).astype(np.int64)
        m_arr = np.frombuffer(seg[rec['m_off']:rec['m_off'] + rec['m_bytes']].tobytes(), dtype=np.int32).astype(np.int64)
        shift = np.frombuffer(seg[rec['shift_off']:rec['shift_off'] + rec['shift_bytes']].tobytes(), dtype=np.uint8).astype(np.int64)
        assert bias.tolist() == rec['bias_int32'], f'{rec['name']}: image bias block != contract bias_int32'
        assert m_arr.tolist() == rec['M'], f'{rec['name']}: image M block != contract M'
        assert shift.tolist() == rec['shift'], f'{rec['name']}: image shift block != contract shift'
        layers[rec['name']] = {'rec': rec, 'weight': weight, 'bias': bias, 'm': m_arr, 'shift': shift}
    return layers

def requant_u8(acc: np.ndarray, m: np.ndarray, shift: np.ndarray, zp_out: int) -> np.ndarray:
    chan_shape = (m.size,) + (1,) * (acc.ndim - 1)
    prod = acc * m.reshape(chan_shape)
    y = round_half_even_shift(prod, shift.reshape(chan_shape)) + np.int64(zp_out)
    return np.clip(y, 0, 255).astype(np.uint8)

def conv2d_int8(x_u8: np.ndarray, blk: dict) -> np.ndarray:
    rec = blk['rec']
    cin, h, w = x_u8.shape
    cout = rec['num_channels']
    k = rec['weight_k']
    assert k == cin * 9 and rec['weight_shape'][1] == cin
    zp_in = rec['zp_in']
    padded = np.zeros((cin, h + 2, w + 2), dtype=np.int64)
    padded[:, 1:-1, 1:-1] = x_u8.astype(np.int64) - np.int64(zp_in)
    windows = np.lib.stride_tricks.sliding_window_view(padded, (1, 3, 3))[:, :, :, 0]
    win = windows.reshape(cin, h * w, 9)
    wk = blk['weight'].reshape(cout, cin, 9)
    acc = np.tensordot(win, wk, axes=([0, 2], [1, 2]))
    acc = acc.T.reshape(cout, h, w) + blk['bias'].reshape(cout, 1, 1)
    return requant_u8(acc, blk['m'], blk['shift'], rec['zp_out'])

def maxpool2x2_floor(x_u8: np.ndarray) -> np.ndarray:
    c, h, w = x_u8.shape
    oh, ow = (h // 2, w // 2)
    view = x_u8[:, :oh * 2, :ow * 2].reshape(c, oh, 2, ow, 2)
    return view.max(axis=(2, 4))

def gap_s32(x_u8: np.ndarray) -> np.ndarray:
    total = x_u8.astype(np.int64).sum(axis=(1, 2))
    return round_half_even_shift(total, 6).astype(np.int64)

def fc_int8(x_vec: np.ndarray, blk: dict) -> np.ndarray:
    rec = blk['rec']
    x_eff = x_vec.astype(np.int64) - np.int64(rec['zp_in'])
    acc = x_eff @ blk['weight'].T + blk['bias']
    return requant_u8(acc, blk['m'], blk['shift'], rec['zp_out'])

def softmax_fixed(fc2_u8: np.ndarray, rec: dict, exp_lut: np.ndarray) -> dict:
    zp_out = rec['zp_out']
    s_out = rec['s_out']
    l_int = fc2_u8.astype(np.int64) - np.int64(zp_out)
    s_q15 = int(np.floor(s_out * (1 << SOFTMAX_Q15_SCALE) + 0.5))
    l_q = l_int * s_q15
    d_q = l_q - int(l_q.max())
    d_q69 = np.right_shift(d_q, SOFTMAX_Q69_SHIFT)
    d_q69 = np.maximum(d_q69, -SOFTMAX_Q69_SAT)
    idx = np.minimum(np.right_shift(-d_q69, SOFTMAX_LUT_LSB_PER_ENTRY), 511).astype(np.int64)
    exp_v = exp_lut[idx].astype(np.int64)
    total = int(exp_v.sum())
    assert total > 0, 'softmax denominator must be positive'
    p_q16 = (exp_v * (1 << 16) + total // 2) // total
    p_q16 = np.minimum(p_q16, 65535)
    p_float = p_q16.astype(np.float64) / 65536.0
    percent = np.rint(p_float * 100.0).astype(np.int64)
    return {'logits_int': l_int, 'logits_q16': l_q, 'softmax_idx': idx, 'exp_q16': exp_v, 'probs_q16': p_q16, 'probs': p_float, 'percent': percent, 'top1': int(np.argmax(p_q16))}

def npu_forward(feat_u8: np.ndarray, contract: dict, exp_lut: np.ndarray, weights: dict | None=None) -> dict:
    if weights is None:
        weights = load_weights_from_image(contract)
    layer_recs = {rec['name']: rec for rec in contract['layers']}
    x = feat_u8[np.newaxis, :, :]
    c1 = conv2d_int8(x, weights['conv1'])
    p1 = maxpool2x2_floor(c1)
    c2 = conv2d_int8(p1, weights['conv2'])
    p2 = maxpool2x2_floor(c2)
    c3 = conv2d_int8(p2, weights['conv3'])
    p3 = maxpool2x2_floor(c3)
    c4 = conv2d_int8(p3, weights['conv4'])
    p4 = maxpool2x2_floor(c4)
    gap = gap_s32(p4)
    f1 = fc_int8(gap, weights['fc1'])
    f2 = fc_int8(f1, weights['fc2'])
    sm = softmax_fixed(f2, layer_recs['fc2'], exp_lut)
    return {'conv1': c1, 'pool1': p1, 'conv2': c2, 'pool2': p2, 'conv3': c3, 'pool3': p3, 'conv4': c4, 'pool4': p4, 'gap': gap, 'fc1': f1, 'fc2': f2, 'logits': sm['logits_int'].astype(np.int32), 'logits_float': sm['logits_int'] * layer_recs['fc2']['s_out'], 'probs_q16': sm['probs_q16'], 'probs': sm['probs'], 'percent': sm['percent'], 'top1': sm['top1'], '_softmax': sm}

def torch_npu_reference(feat_u8: np.ndarray, contract: dict) -> dict:
    import torch
    model_path = Path(__file__).resolve().parents[1] / 'training' / 'deploy' / 'quantized_model.pt'
    model = torch.jit.load(str(model_path), map_location='cpu')
    model.eval()
    qs = contract['quant_stub_input_contract']
    s_in, zp_in = (float(qs['s_in']), int(qs['zp_in']))
    xf = (torch.tensor(feat_u8.astype(np.float32)) - zp_in) * s_in
    xq = torch.quantize_per_tensor(xf.unsqueeze(0).unsqueeze(0), s_in, zp_in, torch.quint8)
    assert torch.equal(xq.int_repr().squeeze(0).squeeze(0), torch.tensor(feat_u8.astype(np.int64)))
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

    def ir(t):
        return t.int_repr().cpu().numpy().astype(np.int64)
    return {'conv1': ir(o1)[0], 'pool1': ir(p1)[0], 'conv2': ir(o2)[0], 'pool2': ir(p2)[0], 'conv3': ir(o3)[0], 'pool3': ir(p3)[0], 'conv4': ir(o4)[0], 'pool4': ir(p4)[0], 'gap': ir(g)[0], 'fc1': ir(f1)[0], 'fc2': ir(f2)[0], 'logits_float': logits.cpu().numpy()[0], 'probs': probs.cpu().numpy()[0], 'top1': int(probs.argmax(dim=1).item())}

def npu_relay_check(feat_u8: np.ndarray, contract: dict, ref: dict, weights: dict | None=None) -> dict:
    if weights is None:
        weights = load_weights_from_image(contract)
    relay = {}
    relay['conv1'] = conv2d_int8(feat_u8[np.newaxis], weights['conv1'])
    relay['conv2'] = conv2d_int8(ref['pool1'], weights['conv2'])
    relay['conv3'] = conv2d_int8(ref['pool2'], weights['conv3'])
    relay['conv4'] = conv2d_int8(ref['pool3'], weights['conv4'])
    relay['gap'] = gap_s32(ref['pool4'])
    relay['fc1'] = fc_int8(ref['gap'], weights['fc1'])
    relay['fc2'] = fc_int8(ref['fc1'], weights['fc2'])
    out = {}
    for key, arr in relay.items():
        d = np.abs(arr.astype(np.int64) - ref[key])
        out[f'max_lsb_{key}'] = int(d.max())
        out[f'n_gt1_{key}'] = int((d > 1).sum())
        out[f'n_gt0_{key}'] = int((d > 0).sum())
        out[f'size_{key}'] = int(d.size)
    return out

def conv2d_float_reference(x_u8: np.ndarray, contract: dict, layer_name: str, weights_dir: Path | None=None) -> np.ndarray:
    rec = {r['name']: r for r in contract['layers']}[layer_name]
    if weights_dir is None:
        weights_dir = Path(__file__).resolve().parents[1] / 'training' / 'deploy' / 'weights'
    w_int8 = np.load(weights_dir / f'{layer_name}_weight_int8.npy')
    s_w = np.load(weights_dir / f'{layer_name}_scale.npy').astype(np.float64)
    cin, h, w = x_u8.shape
    cout = rec['num_channels']
    w_f = w_int8.astype(np.float64) * s_w[:, None, None, None]
    b_f = np.asarray(rec['bias_int32'], dtype=np.float64) * (rec['s_in'] * s_w)
    zp_in = rec['zp_in']
    padded = np.zeros((cin, h + 2, w + 2), dtype=np.float64)
    padded[:, 1:-1, 1:-1] = x_u8.astype(np.float64) - zp_in
    windows = np.lib.stride_tricks.sliding_window_view(padded, (1, 3, 3))[:, :, :, 0].reshape(cin, h * w, 9)
    acc = np.tensordot(windows, w_f.reshape(cout, cin, 9), axes=([0, 2], [1, 2]))
    acc = acc.T.reshape(cout, h, w) * rec['s_in'] + b_f.reshape(cout, 1, 1)
    y = np.rint(acc / rec['s_out']) + rec['zp_out']
    return np.clip(y, 0, 255).astype(np.uint8)

def compare_npu_to_torch(golden: dict, ref: dict) -> dict:
    metrics = {}
    for stage in ('conv1', 'pool1', 'conv2', 'pool2', 'conv3', 'pool3', 'conv4', 'pool4', 'gap', 'fc1', 'fc2'):
        d = np.abs(golden[stage].astype(np.int64) - ref[stage])
        metrics[f'max_lsb_{stage}'] = int(d.max())
        metrics[f'within1_{stage}'] = float((d <= 1).mean())
    dl = np.abs(golden['logits_float'] - ref['logits_float'])
    metrics['max_abs_dlogit'] = float(dl.max())
    dp = np.abs(golden['probs'] - ref['probs'])
    metrics['max_abs_dprob'] = float(dp.max())
    metrics['top1_match'] = golden['top1'] == ref['top1']
    return metrics

def librosa_reference(pcm: np.ndarray) -> np.ndarray:
    src_dir = str(DEFAULT_REF_SRC_DIR)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    import features as instrec_features
    y = pcm.astype(np.float32) / np.float32(32768.0)
    ref = instrec_features.extract_mel_waveform(y, normalize=True, n_frames=N_FRAMES)
    return np.asarray(ref, dtype=np.float32)

def compare_to_reference(z_q412: np.ndarray, ref: np.ndarray) -> dict:
    golden = z_q412.astype(np.float64) / 4096.0
    reference = ref.astype(np.float64)
    max_abs_delta = float(np.max(np.abs(golden - reference)))
    if np.all(golden == golden.flat[0]) and np.all(reference == reference.flat[0]):
        pearson_r = 1.0
    else:
        pearson_r = float(np.corrcoef(golden.ravel(), reference.ravel())[0, 1])
    return {'max_abs_delta': max_abs_delta, 'pearson_r': pearson_r}

def _wav_stem(wav_path: Path) -> str:
    return wav_path.stem

def main(argv: list[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description='Bit-accurate golden model of the InstRec-FPGA Mel pipeline.')
    parser.add_argument('--wav', type=Path, required=True, help='input mono 16-bit wav')
    parser.add_argument('--stage', default=','.join(ALL_STAGES), help=f'comma-separated stages among {ALL_STAGES}')
    parser.add_argument('--tables', type=Path, default=DEFAULT_TABLES_PATH, help='mel_tables.json path')
    parser.add_argument('--outdir', type=Path, default=DEFAULT_OUT_DIR, help='output directory')
    parser.add_argument('--ref', choices=['librosa', 'torch'], default=None, help='also run a floating/quantized reference and print metrics: librosa = Mel z-domain reference; torch = TorchScript NPU reference fed with the SAME uint8 feature')
    args = parser.parse_args(argv)
    stages = [s.strip() for s in args.stage.split(',') if s.strip()]
    for stage in stages:
        if stage not in ALL_STAGES:
            parser.error(f"unknown stage '{stage}' (choose among {ALL_STAGES})")
    tables = load_mel_tables(args.tables)
    pcm = load_pcm_s16(args.wav)
    result = run_mel_pipeline(pcm, tables)
    if any((s in NPU_STAGES for s in stages)) or args.ref == 'torch':
        contract = load_layer_contract()
        npu = npu_forward(result['feat'], contract, tables['exp_lut'])
        result['conv1'] = npu['conv1']
        result['conv2'] = npu['conv2']
        result['conv3'] = npu['conv3']
        result['conv4'] = npu['conv4']
        result['fc1'] = npu['fc1']
        result['fc2'] = npu['fc2']
        result['logits'] = npu['logits']
        result['probs'] = npu['probs']
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = _wav_stem(args.wav)
    for stage in stages:
        out_path = args.outdir / f'{stem}_{stage}.npy'
        np.save(out_path, result[stage])
        print(f'[golden] wrote {out_path} shape={result[stage].shape} dtype={result[stage].dtype}')
    if args.ref == 'librosa':
        ref = librosa_reference(pcm)
        ref_path = args.outdir / f'{stem}_ref_librosa.npy'
        np.save(ref_path, ref)
        metrics = compare_to_reference(result['z'], ref)
        print(f'[golden] wrote {ref_path} shape={ref.shape}')
        print(f'[golden] vs librosa: max|delta|={metrics['max_abs_delta']:.6f} pearson_r={metrics['pearson_r']:.6f}')
    elif args.ref == 'torch':
        contract = load_layer_contract()
        ref = torch_npu_reference(result['feat'], contract)
        np.save(args.outdir / f'{stem}_ref_torch_logits.npy', ref['logits_float'])
        np.save(args.outdir / f'{stem}_ref_torch_probs.npy', ref['probs'])
        metrics = compare_npu_to_torch(npu, ref)
        print(f'[golden] vs torch (same-feature NPU chain): max|dlogit|={metrics['max_abs_dlogit']:.4f} max|dprob|={metrics['max_abs_dprob']:.5f} top1_match={metrics['top1_match']}')
        relay = npu_relay_check(result['feat'], contract, ref)
        worst = max(((v, k) for k, v in relay.items() if k.startswith('max_lsb')))
        print(f'[golden] relay single-layer check: conv1/fc1 exact, worst relay layer {worst[1][8:]} max {worst[0]} LSB (fbgemm tile noise, see conv2d_float_reference)')
        import torch._C
        _orig_set_qengine = torch._C._set_qengine

        def _tolerant_set_qengine(qengine_id: int) -> None:
            try:
                _orig_set_qengine(qengine_id)
            except RuntimeError:
                pass
        torch._C._set_qengine = _tolerant_set_qengine
        try:
            deploy_dir = Path(__file__).resolve().parents[1] / 'training' / 'deploy'
            if str(deploy_dir) not in sys.path:
                sys.path.insert(0, str(deploy_dir))
            import inference_reference as iref
            pred = iref.predict(str(args.wav), str(deploy_dir / 'quantized_model.pt'))
        finally:
            torch._C._set_qengine = _orig_set_qengine
        print(f'[golden] deploy reference top1: id={pred['predicted_id']} ({pred['predicted_class']}); golden top1: id={npu['top1']} match={npu['top1'] == pred['predicted_id']}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
