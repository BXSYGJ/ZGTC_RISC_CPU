from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
import numpy as np
IMAGE_MAGIC = b'IRW1'
HEADER_BYTES = 32
CONTRACT_ENTRY_BYTES = 64
CONTRACT_TABLE_BYTES = 6 * CONTRACT_ENTRY_BYTES
CONTRACT_TABLE_OFFSET = HEADER_BYTES
FIRST_LAYER_OFFSET = 512
ALIGN_BYTES = 32
GROUP_CHANNELS = 16
NUM_LAYERS = 6
FORMAT_VERSION = 1
DDR3_WEIGHT_BASE = 1048576
M_MIN = 1 << 30
M_MAX = 1 << 31
SCALE_MIN = 0.0001
SCALE_MAX = 1.0
ZP_MIN = -128
ZP_MAX = 127
LAYER_SPECS = (('conv1', 'conv', (48, 1, 3, 3), (1, 64, 258), (48, 64, 258)), ('conv2', 'conv', (96, 48, 3, 3), (48, 32, 129), (96, 32, 129)), ('conv3', 'conv', (192, 96, 3, 3), (96, 16, 64), (192, 16, 64)), ('conv4', 'conv', (256, 192, 3, 3), (192, 8, 32), (256, 8, 32)), ('fc1', 'fc', (128, 256), (256,), (128,)), ('fc2', 'fc', (8, 128), (128,), (8,)))
EXPECTED_CLASS_NAMES = ('clarinet', 'distorted electric guitar', 'female singer', 'flute', 'piano', 'tenor saxophone', 'trumpet', 'violin')
EXPECTED_CLASS_NAMES_ZH = ('单簧管', '失真电吉他', '女声', '长笛', '钢琴', '次中音萨克斯', '小号', '小提琴')
DEFAULT_INSTREC_ROOT = Path(__file__).resolve().parents[1] / 'training'
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / 'outputs'
GENERATOR_NAME = 'gen_weight_image.py'
SPEC_REFS = 'tasks.md T-GP-03; design.md 6.1/4.3/5.2/3.7; spec.md REQ-FTR-006'

def load_npy_weights(weights_dir: Path) -> dict:
    layers = {}
    for name, layer_type, weight_shape, _, _ in LAYER_SPECS:
        w = np.load(weights_dir / f'{name}_weight_int8.npy')
        b = np.load(weights_dir / f'{name}_bias_int32.npy')
        s = np.load(weights_dir / f'{name}_scale.npy')
        zp = np.load(weights_dir / f'{name}_zero_point.npy')
        assert tuple(w.shape) == weight_shape, f'{name} weight shape {tuple(w.shape)} != expected {weight_shape}'
        expected_bias_shape = (weight_shape[0],)
        assert tuple(b.shape) == expected_bias_shape, f'{name} bias shape {tuple(b.shape)} != {expected_bias_shape}'
        assert tuple(s.shape) == expected_bias_shape, f'{name} scale shape {tuple(s.shape)} != {expected_bias_shape}'
        assert tuple(zp.shape) == expected_bias_shape, f'{name} zero_point shape {tuple(zp.shape)} != {expected_bias_shape}'
        assert w.dtype == np.int8, f'{name} weight dtype {w.dtype} != int8'
        assert b.dtype == np.int32, f'{name} bias dtype {b.dtype} != int32'
        assert s.dtype == np.float32, f'{name} scale dtype {s.dtype} != float32'
        zp_values = np.asarray(zp).astype(np.int64).ravel()
        assert np.all(zp_values == 0), f'{name} weight zero points are not all zero: {zp_values[:8]}...'
        layers[name] = {'weight_int8': w, 'bias_int32_npy': b.astype(np.int64), 'weight_scale': s.astype(np.float64), 'layer_type': layer_type}
    return layers

def parse_instrument_names(dataset_py: Path) -> tuple:
    import ast
    tree = ast.parse(dataset_py.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and (node.target.id == 'INSTRUMENT_NAMES'):
            names = ast.literal_eval(node.value)
            return tuple(names)
    raise ValueError(f'INSTRUMENT_NAMES not found in {dataset_py}')

def assert_class_order(class_names_json: Path, dataset_py: Path) -> dict:
    with open(class_names_json, 'r', encoding='utf-8') as fh:
        class_info = json.load(fh)
    names = tuple(class_info['names'])
    names_zh = tuple(class_info['name_zh'])
    instrument_names = parse_instrument_names(dataset_py)
    assert names == instrument_names, f'class_names.json order {names} != dataset.py INSTRUMENT_NAMES {instrument_names} (R-06 class-order guard failed)'
    assert names == EXPECTED_CLASS_NAMES, f'class_names.json order {names} != expected {EXPECTED_CLASS_NAMES}'
    assert names_zh == EXPECTED_CLASS_NAMES_ZH, f'class_names.json name_zh {names_zh} != expected {EXPECTED_CLASS_NAMES_ZH}'
    assert class_info['num_classes'] == 8, 'num_classes != 8'
    return {'names': list(names), 'names_zh': list(names_zh)}

def _graph_constant(module, kind: str, index: int):
    graph_text = str(module.forward.graph)
    marker = 'prim::Constant[value='
    values = []
    for line in graph_text.splitlines():
        pos = line.find(marker)
        while pos >= 0:
            start = pos + len(marker)
            end = line.find('](', start)
            token = line[start:end]
            values.append(token)
            pos = line.find(marker, end)
    token = values[index]
    if kind == 'float':
        return float(token)
    return int(token)

def extract_activation_contract(model_path: Path) -> dict:
    import torch
    try:
        torch.backends.quantized.engine = 'fbgemm'
    except RuntimeError:
        pass
    model = torch.jit.load(str(model_path), map_location='cpu')
    model.eval()
    torch.manual_seed(0)
    x = torch.randn(1, 1, 64, 258)
    with torch.no_grad():
        h = model.quant(x)
        quant_stub = {'s_in': float(h.q_scale()), 'zp_in': int(h.q_zero_point()), 'dtype': str(h.dtype)}
        out1 = model.model.conv1(h)
        out2 = model.model.conv2(model.model.pool1(out1))
        out3 = model.model.conv3(model.model.pool2(out2))
        out4 = model.model.conv4(model.model.pool3(out3))
        g = torch.flatten(model.model.gap(model.model.pool4(out4)), 1)
        out_fc1 = model.model.fc1(g)
        out_fc2 = model.model.fc2(out_fc1)
        manual_out = model.dequant(out_fc2)
        ref_out = model(x)
        max_diff = float((manual_out - ref_out).abs().max().item())
        assert max_diff == 0.0, f'manual chain diverged from full forward: max diff {max_diff}'
        z0 = model.quant(torch.zeros(1, 1, 64, 258))
        z1 = model.model.conv1(z0)
        z2 = model.model.conv2(model.model.pool1(z1))
        z3 = model.model.conv3(model.model.pool2(z2))
        z4 = model.model.conv4(model.model.pool3(z3))
        zg = torch.flatten(model.model.gap(model.model.pool4(z4)), 1)
        zf1 = model.model.fc1(zg)
        zf2 = model.model.fc2(zf1)

        def _conv_probe(out_t):
            arr = out_t.int_repr().cpu().numpy()[0].astype(np.int64)
            arr = arr - int(out_t.q_zero_point())
            reps = np.empty(arr.shape[0], dtype=np.int64)
            for c in range(arr.shape[0]):
                vals, cnts = np.unique(arr[c], return_counts=True)
                reps[c] = vals[int(np.argmax(cnts))]
            return reps

        def _fc_probe(out_t):
            arr = out_t.int_repr().cpu().numpy()[0].astype(np.int64)
            return arr - int(out_t.q_zero_point())
        bias_out_probe = {'conv1': _conv_probe(z1), 'conv2': _conv_probe(z2), 'conv3': _conv_probe(z3), 'conv4': _conv_probe(z4), 'fc1': _fc_probe(zf1), 'fc2': _fc_probe(zf2), 'gap': _fc_probe(zg)}
    chain_out = {'conv1': (out1, h), 'conv2': (out2, out1), 'conv3': (out3, out2), 'conv4': (out4, out3), 'fc1': (out_fc1, out4), 'fc2': (out_fc2, out_fc1)}
    layers = {}
    for name, (out_t, in_t) in chain_out.items():
        layers[name] = {'s_in': float(in_t.q_scale()), 'zp_in': int(in_t.q_zero_point()), 's_out': float(out_t.q_scale()), 'zp_out': int(out_t.q_zero_point()), 'dtype': str(out_t.dtype)}

    def _read_param(module, attr):
        value = getattr(module, attr)
        if callable(value):
            value = value()
        if hasattr(value, 'item'):
            value = value.item()
        return value
    for name in ('conv1', 'conv2', 'conv3', 'conv4'):
        mod = getattr(model.model, name)
        s_attr = float(_read_param(mod, 'scale'))
        zp_attr = int(_read_param(mod, 'zero_point'))
        assert s_attr == layers[name]['s_out'], f'{name} module scale() {s_attr} != chained {layers[name]['s_out']}'
        assert zp_attr == layers[name]['zp_out'], f'{name} module zero_point() {zp_attr} != chained {layers[name]['zp_out']}'
    for name in ('fc1', 'fc2'):
        mod = getattr(model.model, name)
        s_const = _graph_constant(mod, 'float', 0)
        zp_const = _graph_constant(mod, 'int', 1)
        assert s_const == layers[name]['s_out'], f'{name} graph scale constant {s_const} != chained {layers[name]['s_out']}'
        assert zp_const == layers[name]['zp_out'], f'{name} graph zero-point constant {zp_const} != chained {layers[name]['zp_out']}'
    return {'quant_stub': quant_stub, 'layers': layers, 'bias_out_probe': bias_out_probe, '_probe_tensors': {'x_int': h.int_repr().cpu().numpy(), 'conv1_int': out1.int_repr().cpu().numpy(), 'gap_int': g.int_repr().cpu().numpy(), 'fc1_int': out_fc1.int_repr().cpu().numpy(), 'fc2_int': out_fc2.int_repr().cpu().numpy()}}

def assert_activation_sanity(activation: dict) -> None:
    entries = [activation['quant_stub']] + [{'s_in': rec['s_in'], 'zp_in': rec['zp_in']} for rec in activation['layers'].values()] + list(activation['layers'].values())
    for idx, rec in enumerate(entries):
        for key_s in ('s_in', 's_out'):
            if key_s in rec:
                assert SCALE_MIN < rec[key_s] < SCALE_MAX, f'entry {idx} {key_s}={rec[key_s]} outside ({SCALE_MIN}, {SCALE_MAX}) (R-12)'
        for key_zp in ('zp_in', 'zp_out'):
            if key_zp in rec:
                assert ZP_MIN <= rec[key_zp] <= ZP_MAX, f'entry {idx} {key_zp}={rec[key_zp]} outside [{ZP_MIN}, {ZP_MAX}] (R-12)'

def cross_check_packed_weights(model_path: Path, npy_weights: dict) -> dict:
    import torch
    model = torch.jit.load(str(model_path), map_location='cpu')
    model.eval()
    float_bias = {}
    for name, layer_type, weight_shape, _, _ in LAYER_SPECS:
        mod = getattr(model.model, name)
        if layer_type == 'conv':
            w_q, b_q = torch.ops.quantized.conv2d_unpack(mod._packed_params)
        else:
            raw = mod._packed_params._packed_params
            w_q, b_q = torch.ops.quantized.linear_unpack(raw)
        w_pt = w_q.int_repr().cpu().numpy().astype(np.int8)
        s_pt = w_q.q_per_channel_scales().detach().cpu().numpy()
        zp_pt = w_q.q_per_channel_zero_points().detach().cpu().numpy()
        b_f = b_q.detach().cpu().numpy().astype(np.float64)
        float_bias[name] = b_f
        npy = npy_weights[name]
        assert tuple(w_pt.shape) == weight_shape, f'{name}: pt weight shape {tuple(w_pt.shape)} != {weight_shape}'
        assert np.array_equal(w_pt, npy['weight_int8']), f'{name}: npy int8 weights differ from TorchScript weights'
        assert np.array_equal(s_pt, npy['weight_scale'].astype(np.float32)), f'{name}: npy weight scales differ from TorchScript scales'
        assert np.all(zp_pt == 0), f'{name}: TorchScript weight zp != 0'
        truncated = np.trunc(b_f).astype(np.int64)
        assert np.array_equal(truncated, npy['bias_int32_npy']), f'{name}: npy bias is not the truncation of the float bias; unexpected source mismatch'
    return float_bias

def requantize(acc: np.ndarray, m: np.ndarray, shift: np.ndarray, zp_out: int, unsigned: bool) -> np.ndarray:
    chan_shape = (len(m),) + (1,) * (acc.ndim - 1)
    m_b = m.reshape(chan_shape)
    shift_b = shift.reshape(chan_shape)
    prod = acc * m_b
    shifted = prod >> shift_b
    y = shifted + zp_out
    if unsigned:
        return np.clip(y, 0, 255)
    return np.clip(y, -128, 127)

def numerical_cross_check(activation: dict, npy_weights: dict, m_shift: dict, bias_int32: dict) -> dict:
    probe = activation['_probe_tensors']
    tol = 1
    w1 = npy_weights['conv1']['weight_int8'].astype(np.int64)
    b1 = bias_int32['conv1']
    x_int = probe['x_int'][0, 0].astype(np.int64)
    zp_in = activation['layers']['conv1']['zp_in']
    wsum1 = w1.reshape(48, -1).sum(axis=1)
    padded = np.full((x_int.shape[0] + 2, x_int.shape[1] + 2), zp_in, dtype=np.int64)
    padded[1:-1, 1:-1] = x_int
    windows = np.lib.stride_tricks.sliding_window_view(padded, (3, 3))
    windows = windows.reshape(windows.shape[0], windows.shape[1], 9)
    acc = np.einsum('yxw,cw->cyx', windows, w1.reshape(48, 9))
    acc = acc + b1[:, None, None] - zp_in * wsum1[:, None, None]
    y1 = requantize(acc, m_shift['conv1']['m'], m_shift['conv1']['shift'], activation['layers']['conv1']['zp_out'], unsigned=True)
    ref1 = probe['conv1_int'][0].astype(np.int64)
    diff1 = int(np.abs(y1 - ref1).max())
    assert diff1 <= tol, f'conv1 manual vs TorchScript: max diff {diff1} > {tol}'
    w_f1 = npy_weights['fc1']['weight_int8'].astype(np.int64)
    b_f1 = bias_int32['fc1']
    g_int = probe['gap_int'][0].astype(np.int64)
    wsum_f1 = w_f1.sum(axis=1)
    acc_f1 = g_int @ w_f1.T + b_f1 - activation['layers']['fc1']['zp_in'] * wsum_f1
    y_f1 = requantize(acc_f1, m_shift['fc1']['m'], m_shift['fc1']['shift'], activation['layers']['fc1']['zp_out'], unsigned=True)
    ref_f1 = probe['fc1_int'][0].astype(np.int64)
    diff_f1 = int(np.abs(y_f1 - ref_f1).max())
    assert diff_f1 <= tol, f'fc1 manual vs TorchScript: max diff {diff_f1} > {tol}'
    w_f2 = npy_weights['fc2']['weight_int8'].astype(np.int64)
    b_f2 = bias_int32['fc2']
    wsum_f2 = w_f2.sum(axis=1)
    fc1_ref = probe['fc1_int'][0].astype(np.int64)
    acc_f2 = fc1_ref @ w_f2.T + b_f2 - activation['layers']['fc2']['zp_in'] * wsum_f2
    y_f2 = requantize(acc_f2, m_shift['fc2']['m'], m_shift['fc2']['shift'], activation['layers']['fc2']['zp_out'], unsigned=True)
    ref_f2 = probe['fc2_int'][0].astype(np.int64)
    diff_f2 = int(np.abs(y_f2 - ref_f2).max())
    assert diff_f2 <= tol, f'fc2 manual vs TorchScript: max diff {diff_f2} > {tol}'
    return {'conv1': diff1, 'fc1': diff_f1, 'fc2': diff_f2}

def compute_bias_int32(npy_weights: dict, activation: dict, float_bias: dict) -> tuple:
    layers = activation['layers']
    probe = activation['bias_out_probe']
    bias = {}
    sources = {}
    for name, layer_type, weight_shape, _, _ in LAYER_SPECS:
        act = layers[name]
        s_w = npy_weights[name]['weight_scale']
        b_f = float_bias[name]
        b_q = np.round(b_f / (act['s_in'] * s_w)).astype(np.int64)
        bias[name] = b_q
        sources[name] = 'pt_packed_params_float_bias'
    x_eff = np.zeros(1, dtype=np.int64)
    for name, layer_type, weight_shape, _, _ in LAYER_SPECS:
        act = layers[name]
        w = npy_weights[name]['weight_int8'].reshape(weight_shape)
        s_w = npy_weights[name]['weight_scale']
        ratio = s_w * (act['s_in'] / act['s_out'])
        if layer_type == 'conv':
            cin = weight_shape[1]
            k = weight_shape[2] * weight_shape[3]
            w_sum = w.astype(np.int64).reshape(-1, cin, k).sum(axis=2)
        else:
            w_sum = w.astype(np.int64)
        acc = x_eff @ w_sum.T + bias[name]
        out_val = np.round(acc * ratio)
        if name != 'fc2':
            out_val = np.maximum(out_val, 0.0)
        out_int = np.clip(out_val + act['zp_out'], 0, 255).astype(np.int64)
        expected_probe = out_int - act['zp_out']
        delta = np.abs(expected_probe - probe[name])
        assert int(delta.max()) <= 1, f'{name}: recursive probe check disagrees by {int(delta.max())} LSB (contract inconsistency)'
        if name == 'conv4':
            x_eff = probe['gap']
        else:
            x_eff = probe[name] + act['zp_out']
    return (bias, sources)

def compute_m_shift(ratio: float) -> tuple:
    if not ratio > 0.0:
        raise ValueError(f'ratio must be positive, got {ratio!r}')
    if round(ratio) >= M_MAX:
        raise ValueError(f'ratio={ratio!r} >= 2^31: no non-negative shift keeps M in [2^30, 2^31)')
    if round(ratio * 2.0 ** 63) < M_MIN:
        raise ValueError(f'ratio={ratio!r} too small: even shift=63 cannot lift M to [2^30, 2^31)')
    shift = int(math.floor(math.log2(float(M_MAX) / ratio))) + 1
    while round(ratio * 2.0 ** shift) >= M_MAX or shift > 63:
        shift -= 1
    while round(ratio * 2.0 ** (shift + 1)) < M_MAX and shift < 63:
        shift += 1
    while round(ratio * 2.0 ** shift) < M_MIN and shift < 63:
        shift += 1
    m = int(round(ratio * 2.0 ** shift))
    if not M_MIN <= m < M_MAX:
        raise ValueError(f'M={m} shift={shift} out of [2^30, 2^31) for ratio={ratio!r}')
    if not 0 <= shift <= 63:
        raise ValueError(f'shift={shift} exceeds 6-bit range for ratio={ratio!r}')
    return (m, shift)

def compute_layer_m_shift(npy_weights: dict, activation: dict) -> dict:
    result = {}
    for name, _, _, _, _ in LAYER_SPECS:
        act = activation['layers'][name]
        s_w = npy_weights[name]['weight_scale']
        s_in = act['s_in']
        s_out = act['s_out']
        ratio = s_w * (s_in / s_out)
        m_list = []
        shift_list = []
        for r in ratio:
            m_c, s_c = compute_m_shift(float(r))
            m_list.append(m_c)
            shift_list.append(s_c)
        m_arr = np.asarray(m_list, dtype=np.int64)
        shift_arr = np.asarray(shift_list, dtype=np.int64)
        assert np.all((m_arr >= M_MIN) & (m_arr < M_MAX)), f'{name}: M outside [2^30, 2^31)'
        result[name] = {'m': m_arr, 'shift': shift_arr, 'ratio': ratio}
    return result

def choose_inv_s_in(s_in: float) -> dict:
    q16 = int(round(2 ** 16 / s_in))
    if 0 < q16 <= 65535:
        return {'format': 'Q16.16', 'bits': 16, 'value': q16}
    q24 = int(round(2 ** 24 / s_in))
    if 0 < q24 <= 2147483647:
        return {'format': 'Q8.24', 'bits': 32, 'value': q24}
    raise ValueError(f'inv_s_in for s_in={s_in!r} overflows the Q8.24 s32 container (value {q24}); no Q-format escalation defined in design.md 3.7')
EXPECTED_GROUP_WEIGHT_BYTES = {'conv1': 144, 'conv2': 6912, 'conv3': 13824, 'conv4': 27648, 'fc1': 4096, 'fc2': 1024}

def interleave_group_major(weight_2d: np.ndarray, group_channels: int=GROUP_CHANNELS) -> np.ndarray:
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

def segment_checksum_128(payload: bytes) -> bytes:
    acc = 0
    for i in range(0, len(payload), 16):
        chunk = payload[i:i + 16]
        if len(chunk) < 16:
            chunk = chunk + b'\x00' * (16 - len(chunk))
        acc = (acc + int.from_bytes(chunk, 'little')) % (1 << 128)
    return acc.to_bytes(16, 'little')

def pack_contract_entry(layer: dict) -> bytes:
    dtype_code = 0 if layer['activation_dtype'] == 'torch.quint8' else 1
    in_c, in_h, in_w = layer['in_shape_padded']
    out_c, out_h, out_w = layer['out_shape_padded']
    entry = struct.pack('<HBBHHIIIIIIbbBBHHHHIHHIII', 19523, layer['layer_id'], 0 if layer['layer_type'] == 'conv' else 1, layer['num_groups'], layer['num_channels'], layer['image_offset'], layer['segment_bytes'], layer['weight_bytes'], layer['bias_off'], layer['m_off'], layer['shift_off'], layer['zp_in'], layer['zp_out'], dtype_code, layer['last_group_channels'], in_c, in_w, out_c, out_w, layer['weight_k'], in_h, out_h, 0, 0, 0)
    assert len(entry) == CONTRACT_ENTRY_BYTES, f'contract entry packed to {len(entry)} bytes, expected {CONTRACT_ENTRY_BYTES}'
    return entry

def build_image(npy_weights: dict, activation: dict, m_shift: dict, bias_int32: dict, bias_sources: dict) -> tuple:
    segments = []
    layer_records = []
    offset = FIRST_LAYER_OFFSET
    for layer_id, (name, layer_type, weight_shape, in_shape, out_shape) in enumerate(LAYER_SPECS):
        npy = npy_weights[name]
        act = activation['layers'][name]
        ms = m_shift[name]
        weight = npy['weight_int8']
        cout = weight_shape[0]
        if layer_type == 'conv':
            cin = weight_shape[1]
            weight_k = cin * weight_shape[2] * weight_shape[3]
            in_shape_padded = in_shape
            out_shape_padded = out_shape
        else:
            cin = weight_shape[1]
            weight_k = cin
            in_shape_padded = (in_shape[0], 1, 1)
            out_shape_padded = (out_shape[0], 1, 1)
        weight_2d = weight.reshape(cout, weight_k)
        interleaved = interleave_group_major(weight_2d)
        weight_bytes = interleaved.astype(np.int8).tobytes()
        num_groups = (cout + GROUP_CHANNELS - 1) // GROUP_CHANNELS
        expected_group = EXPECTED_GROUP_WEIGHT_BYTES[name]
        assert len(weight_bytes) == num_groups * expected_group, f'{name}: interleaved weight bytes {len(weight_bytes)} != {num_groups} groups x {expected_group} B (design.md 4.1)'
        bias_bytes = bias_int32[name].astype(np.int32).tobytes()
        m_bytes = ms['m'].astype(np.int32).tobytes()
        shift_bytes = ms['shift'].astype(np.uint8).tobytes()
        bias_off = len(weight_bytes)
        m_off = bias_off + len(bias_bytes)
        shift_off = m_off + len(m_bytes)
        segment_bytes = shift_off + len(shift_bytes)
        padded_len = (segment_bytes + ALIGN_BYTES - 1) // ALIGN_BYTES * ALIGN_BYTES
        wsum = weight.reshape(cout, -1).sum(axis=1).astype(np.int32)
        layer_records.append({'name': name, 'layer_id': layer_id, 'layer_type': layer_type, 's_in': act['s_in'], 'zp_in': act['zp_in'], 's_out': act['s_out'], 'zp_out': act['zp_out'], 'activation_dtype': act['dtype'], 'weight_scale_min': float(npy['weight_scale'].min()), 'weight_scale_max': float(npy['weight_scale'].max()), 'm': ms['m'].tolist(), 'shift': ms['shift'].tolist(), 'm_min': int(ms['m'].min()), 'm_max': int(ms['m'].max()), 'shift_min': int(ms['shift'].min()), 'shift_max': int(ms['shift'].max()), 'num_channels': cout, 'num_groups': (cout + GROUP_CHANNELS - 1) // GROUP_CHANNELS, 'group_channels': GROUP_CHANNELS, 'last_group_channels': cout - ((cout + GROUP_CHANNELS - 1) // GROUP_CHANNELS - 1) * GROUP_CHANNELS, 'weight_k': weight_k, 'weight_shape': list(weight_shape), 'in_shape': list(in_shape), 'out_shape': list(out_shape), 'in_shape_padded': list(in_shape_padded), 'out_shape_padded': list(out_shape_padded), 'weight_bytes': len(weight_bytes), 'bias_bytes': len(bias_bytes), 'm_bytes': len(m_bytes), 'shift_bytes': len(shift_bytes), 'segment_bytes': segment_bytes, 'image_offset': offset, 'ddr3_offset': DDR3_WEIGHT_BASE + offset, 'bias_off': bias_off, 'm_off': m_off, 'shift_off': shift_off, 'bias_int32': bias_int32[name].tolist(), 'bias_source': bias_sources[name], 'bias_out_probe': activation['bias_out_probe'][name].tolist(), 'padding_value': act['zp_in'], 'zp_in_correction': {'enabled': act['zp_in'] != 0, 'zp_in': act['zp_in'], 'wsum': wsum.tolist()}})
        segments.append((name, weight_bytes + bias_bytes + m_bytes + shift_bytes, padded_len))
        offset += padded_len
    contract_table = b''.join((pack_contract_entry(rec) for rec in layer_records))
    assert len(contract_table) == CONTRACT_TABLE_BYTES
    payload = bytearray(contract_table)
    gap = FIRST_LAYER_OFFSET - CONTRACT_TABLE_OFFSET - len(contract_table)
    assert gap >= 0, 'contract table overruns the first-layer offset'
    payload += b'\x00' * gap
    for _, content, padded_len in segments:
        payload += content
        payload += b'\x00' * (padded_len - len(content))
    payload = bytes(payload)
    payload_offset = CONTRACT_TABLE_OFFSET
    assert FIRST_LAYER_OFFSET - payload_offset == len(contract_table) + gap
    total_bytes = HEADER_BYTES + len(payload)
    checksum = segment_checksum_128(payload)
    header = struct.pack('<4sHHII16s', IMAGE_MAGIC, NUM_LAYERS, FORMAT_VERSION, total_bytes, len(payload), checksum)
    assert len(header) == HEADER_BYTES
    image = header + payload
    assert len(image) == total_bytes
    layout = {'header_offset': 0, 'header_bytes': HEADER_BYTES, 'contract_table_offset': CONTRACT_TABLE_OFFSET, 'contract_table_bytes': CONTRACT_TABLE_BYTES, 'first_layer_offset': FIRST_LAYER_OFFSET, 'total_bytes': total_bytes, 'payload_bytes': len(payload), 'payload_checksum_128': checksum.hex(), 'regions': [{'name': rec['name'], 'offset': rec['image_offset'], 'bytes': rec['segment_bytes']} for rec in layer_records]}
    return (image, layer_records, layout)

def build_contract_json(activation: dict, layer_records: list, layout: dict, classes: dict, image_sha256: str) -> dict:
    quant_stub = activation['quant_stub']
    inv_s_in = choose_inv_s_in(quant_stub['s_in'])
    return {'generator': GENERATOR_NAME, 'spec_refs': SPEC_REFS, 'format_version': FORMAT_VERSION, 'image_magic': IMAGE_MAGIC.decode('ascii'), 'image_sha256': image_sha256, 'image_total_bytes': layout['total_bytes'], 'payload_checksum_128': layout['payload_checksum_128'], 'ddr3_weight_base': DDR3_WEIGHT_BASE, 'ddr3_weight_base_hex': f'0x{DDR3_WEIGHT_BASE:08X}', 'determinism': 'byte-identical on re-run: fixed probe seed, pure integer packing, json floats round-trip via repr', 'requant_formula': 'y = sat((acc_s32 * M[c]) >>> shift[c] + zp_out); M[c] = round(s_w[c] * s_in / s_out * 2^shift[c]), M[c] in [2^30, 2^31) (Q0.31)', 'activation_dtype_note': 'all activations are torch.quint8 (fbgemm unsigned 8-bit); conv1 input zp_in=49 requires the -zp_in*sum(w) accumulator correction (zp_in_correction.wsum) AND zero-padding with padding_value == zp_in (49), not 0', 'bias_note': 'InstRec deploy/weights/*_bias_int32.npy is corrupted: the export did .astype(np.int32) on the FLOAT32 fbgemm bias (every |bias|<1 truncated to 0). This tool rebuilds the int32 biases from the TorchScript source: conv1..4 from the packed-params float bias (exact), fc1/fc2 from a zero-input probe (accurate to 0.5 output LSB). See layers[].bias_source.', 'quant_stub_input_contract': {'description': 'Mel -> int8 quantization contract (REQ-FTR-006): x_q = sat_u8(round_even(z * inv_s_in >> frac_bits) + zp_in)', 's_in': quant_stub['s_in'], 'zp_in': quant_stub['zp_in'], 'dtype': quant_stub['dtype'], 'inv_s_in': inv_s_in['value'], 'inv_s_in_format': inv_s_in['format'], 'inv_s_in_bits': inv_s_in['bits']}, 'classes': {'num_classes': 8, 'names': classes['names'], 'names_zh': classes['names_zh'], 'asserted_against': 'InstRec/src/dataset.py INSTRUMENT_NAMES (R-06 guard); deploy/irmas/model_config.json classes intentionally ignored (stale metadata, design.md F-13)'}, 'layers': [{'name': rec['name'], 'layer_id': rec['layer_id'], 'layer_type': rec['layer_type'], 's_in': rec['s_in'], 's_out': rec['s_out'], 'zp_in': rec['zp_in'], 'zp_out': rec['zp_out'], 'activation_dtype': rec['activation_dtype'], 'M': rec['m'], 'shift': rec['shift'], 'M_min': rec['m_min'], 'M_max': rec['m_max'], 'shift_min': rec['shift_min'], 'shift_max': rec['shift_max'], 'weight_scale_min': rec['weight_scale_min'], 'weight_scale_max': rec['weight_scale_max'], 'num_groups': rec['num_groups'], 'num_channels': rec['num_channels'], 'group_channels': rec['group_channels'], 'last_group_channels': rec['last_group_channels'], 'weight_k': rec['weight_k'], 'weight_shape': rec['weight_shape'], 'in_shape': rec['in_shape'], 'out_shape': rec['out_shape'], 'weight_bytes': rec['weight_bytes'], 'bias_bytes': rec['bias_bytes'], 'm_bytes': rec['m_bytes'], 'shift_bytes': rec['shift_bytes'], 'segment_bytes': rec['segment_bytes'], 'image_offset': rec['image_offset'], 'ddr3_offset': rec['ddr3_offset'], 'ddr3_offset_hex': f'0x{rec['ddr3_offset']:08X}', 'bias_off': rec['bias_off'], 'm_off': rec['m_off'], 'shift_off': rec['shift_off'], 'bias_int32': rec['bias_int32'], 'bias_source': rec['bias_source'], 'bias_out_probe': rec['bias_out_probe'], 'padding_value': rec['padding_value'], 'zp_in_correction': rec['zp_in_correction']} for rec in layer_records], 'image_layout': layout}

def generate(instrec_root: Path, out_dir: Path) -> tuple:
    weights_dir = instrec_root / 'deploy' / 'weights'
    model_path = instrec_root / 'deploy' / 'quantized_model.pt'
    class_names_json = instrec_root / 'deploy' / 'class_names.json'
    dataset_py = instrec_root / 'src' / 'dataset.py'
    for required in (weights_dir, model_path, class_names_json, dataset_py):
        if not required.exists():
            raise FileNotFoundError(f'missing required source: {required}')
    classes = assert_class_order(class_names_json, dataset_py)
    npy_weights = load_npy_weights(weights_dir)
    activation = extract_activation_contract(model_path)
    assert_activation_sanity(activation)
    float_bias = cross_check_packed_weights(model_path, npy_weights)
    bias_int32, bias_sources = compute_bias_int32(npy_weights, activation, float_bias)
    m_shift = compute_layer_m_shift(npy_weights, activation)
    numerical_cross_check(activation, npy_weights, m_shift, bias_int32)
    image, layer_records, layout = build_image(npy_weights, activation, m_shift, bias_int32, bias_sources)
    image_sha256 = hashlib.sha256(image).hexdigest()
    contract = build_contract_json(activation, layer_records, layout, classes, image_sha256)
    out_dir.mkdir(parents=True, exist_ok=True)
    bin_path = out_dir / 'weights_image.bin'
    json_path = out_dir / 'layer_contract.json'
    bin_path.write_bytes(image)
    with open(json_path, 'w', encoding='utf-8', newline='\n') as fh:
        json.dump(contract, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    return (image, contract)

def main(argv: list | None=None) -> int:
    parser = argparse.ArgumentParser(description='Generate the DDR3 weight image and layer contract.')
    parser.add_argument('--instrec-root', type=Path, default=DEFAULT_INSTREC_ROOT, help='InstRec project root (default: %(default)s)')
    parser.add_argument('--outdir', type=Path, default=DEFAULT_OUT_DIR, help='output directory (default: %(default)s)')
    args = parser.parse_args(argv)
    image, contract = generate(args.instrec_root, args.outdir)
    bin_path = args.outdir / 'weights_image.bin'
    json_path = args.outdir / 'layer_contract.json'
    sha = hashlib.sha256(image).hexdigest()
    print(f'[gen_weight_image] wrote {bin_path} ({len(image)} bytes)')
    print(f'[gen_weight_image] wrote {json_path}')
    print(f'[gen_weight_image] image sha256: {sha}')
    print(f'[gen_weight_image] payload 128-bit checksum: {contract['payload_checksum_128']}')
    for layer in contract['layers']:
        print(f'  {layer['name']:5s} {layer['layer_type']:4s} Cout={layer['num_channels']:3d} groups={layer['num_groups']:2d} shift[{layer['shift_min']}..{layer['shift_max']}] M[{layer['M_min']}..{layer['M_max']}] ddr3=0x{layer['ddr3_offset']:08X} zp_in={layer['zp_in']} zp_out={layer['zp_out']}')
    return 0
if __name__ == '__main__':
    sys.exit(main())
