"""Fixed-feature NPU probe: per-layer RTL snapshots for board-side comparison.

B-package (numeric localization / NPU) M0 deliverable: deterministic
feature vectors driven through the complete native-controller NPU chain
(the exact RTL set validated by sim/experiments/npu_full_native), with
every layer output exported as a binary snapshot plus a JSON baseline
report.  This is the golden truth source for future board-side
three-level injection comparison (feature / PCM / I2S).

Probe vectors (fixed, deterministic, in this order):
  v0 sine440           real mel feature of tests/fixtures/sine_440_full.wav,
                       recomputed bit-exactly via golden_pipeline.run_mel_pipeline
  v1 zeros49           all-49 anchor: zp_in domain zero = digital silence
  v2 rand20261104      deterministic pseudo-random uint8 (PCG64 seed 20261104)
  v3 sine440_twolevel  real mel feature of tests/fixtures/sine_440_twolevel.wav

No other-class golden sample exists under reports/golden_ref/ or
tests/fixtures/ (only sine variants and silence); recorded as-is.

Golden truth source: scripts/golden_pipeline.py bit-level path ONLY.
Torch is never used (its QEngine carries 21..67 LSB fbgemm tile noise).

Outputs (gitignored / rebuildable except the report):
  build/sim/npu_probe/assets/          weights.hex + feat_v*.hex
  build/sim/npu_probe/<vector>/*.hex   raw RTL dumps ($writememh)
  build/sim/npu_probe/<vector>/*.bin   layer snapshots (layouts in report)
  reports/npu_probe_baseline_20261104.json (default --report path)

Usage (from instrec_fpga/):
  python sim/experiments/npu_probe/run.py                # all 4 vectors
  python sim/experiments/npu_probe/run.py --vectors 2    # first 2 only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]          # instrec_fpga/
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'scripts'))
import run_sim as sim                                # noqa: E402
import golden_pipeline as golden                     # noqa: E402

PROBE_BUILD = ROOT / 'build/sim/npu_probe'
ASSETS = PROBE_BUILD / 'assets'
REPORT_PATH = ROOT / 'reports/npu_probe_baseline_20261104.json'
GOLDEN_REF = ROOT / 'reports/golden_ref/sine_440_full'
ZP_OUT_FC2 = 57
PRNG_SEED = 20261104
CASE_NAME = 'npu_probe'
EXE_PATH = PROBE_BUILD / 'obj' / ('sim_%s.exe' % CASE_NAME)

# (bin name, hex file, element count, container type)
LAYER_SPECS = [
    ('conv1', 'conv1', 792576, 'u8'),
    ('conv2', 'conv2', 396288, 'u8'),
    ('conv3', 'conv3', 196608, 'u8'),
    ('conv4', 'conv4', 65536, 'u8'),
    ('pool1', 'pool1', 198144, 'u8'),
    ('pool2', 'pool2', 98304, 'u8'),
    ('pool3', 'pool3', 49152, 'u8'),
    ('pool4', 'pool4', 16384, 'u8'),
    ('gap', 'gap', 256, 's32'),
    ('fc1', 'fc1', 128, 'u8'),
    ('fc2', 'fc2', 8, 'u8'),
    ('probs_q16', 'probs', 8, 'u16'),
]

VECTOR_ORDER = ['sine440', 'zeros49', 'rand20261104', 'sine440_twolevel']


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_hex(path: Path, values, digits: int) -> None:
    """$readmemh format: one value per line, zero padded, masked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = (1 << (4 * digits)) - 1
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write('\n'.join(format(int(v) & mask, '0%dx' % digits) for v in values))
        fh.write('\n')


def read_hex(path: Path) -> list:
    with open(path, 'r', encoding='ascii') as fh:
        return [int(tok, 16) for tok in fh.read().split() if tok]


def golden_stream(name: str, res: dict) -> np.ndarray:
    """Golden layer array in the RTL output stream order (int64 values).

    conv/pool maps (C,H,W) interleave to (row, group, col, lane) exactly
    like the parent experiment's expected-value hex files; flat vectors
    pass through unchanged.
    """
    a = res[name]
    if a.ndim == 3:
        c, h, w = a.shape
        return a.reshape(c // 16, 16, h, w).transpose(2, 0, 3, 1).reshape(-1).astype(np.int64)
    return np.asarray(a).astype(np.int64)


def layer_stats(arr: np.ndarray) -> dict:
    """Snapshot statistics on the semantic (signed for s32) int64 view."""
    flat = np.asarray(arr, dtype=np.int64).reshape(-1)
    return {
        'elements': int(flat.size),
        'first': int(flat[0]),
        'last': int(flat[-1]),
        'min': int(flat.min()),
        'max': int(flat.max()),
        'sum_int64': int(flat.sum(dtype=np.int64)),
    }


def build_vectors() -> list:
    """Deterministic probe vectors (fixed order, fixed seeds)."""
    tables = golden.load_mel_tables()
    vectors = []

    t0 = time.time()
    pcm = golden.load_pcm_s16(ROOT / 'tests/fixtures/sine_440_full.wav')
    feat_sine = golden.run_mel_pipeline(pcm, tables)['feat']
    ref_feat = np.load(GOLDEN_REF / 'feat.npy')
    assert np.array_equal(feat_sine, ref_feat), (
        'sine440 mel recompute differs from reports/golden_ref/sine_440_full/feat.npy')
    vectors.append({
        'name': 'sine440', 'kind': 'mel_sine_440', 'feat': feat_sine,
        'source': 'tests/fixtures/sine_440_full.wav via golden_pipeline.run_mel_pipeline (bit-exact, cross-checked against reports/golden_ref/sine_440_full/feat.npy)',
    })

    vectors.append({
        'name': 'zeros49', 'kind': 'const_zp_in',
        'feat': np.full((64, 258), 49, dtype=np.uint8),
        'source': 'all-49 constant: zp_in-domain zero (digital silence anchor; librosa-parity all-silent path also yields all-49)',
    })

    vectors.append({
        'name': 'rand20261104', 'kind': 'prng_uint8',
        'feat': np.random.default_rng(PRNG_SEED).integers(
            0, 256, size=(64, 258), dtype=np.uint8),
        'source': 'numpy PCG64 default_rng(seed=%d).integers(0,256,(64,258),uint8)' % PRNG_SEED,
    })

    pcm2 = golden.load_pcm_s16(ROOT / 'tests/fixtures/sine_440_twolevel.wav')
    feat_two = golden.run_mel_pipeline(pcm2, tables)['feat']
    vectors.append({
        'name': 'sine440_twolevel', 'kind': 'mel_sine_440_twolevel',
        'feat': feat_two,
        'source': 'tests/fixtures/sine_440_twolevel.wav via golden_pipeline.run_mel_pipeline',
    })
    print('mel recompute + vector build: %.1f s' % (time.time() - t0))
    return vectors


def write_assets(vectors: list) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    weights = np.fromfile(str(ROOT / 'scripts/outputs/weights_image.bin'), dtype=np.uint8)
    write_hex(ASSETS / 'weights.hex', weights, 2)
    for i, vec in enumerate(vectors):
        write_hex(ASSETS / ('feat_v%d.hex' % i), vec['feat'].reshape(-1), 2)
    # the TB always $readmemh's all four feat files: emit placeholders for
    # any vector beyond the selection so the load cannot fail.
    for i in range(len(vectors), 4):
        write_hex(ASSETS / ('feat_v%d.hex' % i), np.zeros(16512, np.uint8), 2)


def rtl_file_list() -> list:
    """Identical RTL set to sim/experiments/npu_full_native/run.py."""
    rtl = [HERE.parent / 'npu_full_end/conv_engine_candidate.v',
           HERE.parent / 'npu_full_end/pool_engine_candidate.v',
           HERE.parent / 'npu_full_end/npu_top_candidate.v',
           HERE.parent / 'npu_full_end/fc_engine.v',
           HERE.parent / 'npu_full_end/wbuf.v',
           ROOT / 'sim/experiments/wdma_parameter_ram/wdma_wide_fixed.v',
           ROOT / 'sim/experiments/activation_store/activation_row_store_dynamic.v',
           ROOT / 'sim/experiments/activation_store/activation_store_mux.v',
           ROOT / 'sim/experiments/npu_lifecycle/npu_stage_lifecycle.v']
    rtl += [ROOT / ('src/npu/' + name + '.v') for name in
            ('gap_unit', 'requant_unit', 'softmax_top')]
    rtl += [HERE.parent / 'npu_pingpong_native/weight_read_aligner.v',
            HERE.parent / 'npu_pingpong_native/ddr3_axi_model_full.sv',
            ROOT / 'src/ddr3/ddr3_ctrl_axi.v',
            ROOT / 'sim/experiments/npu_lifecycle/ddr3_arbiter.v',
            ROOT / 'sim/experiments/npu_m1_bridge/npu_m1_bridge.v']
    missing = [str(p) for p in rtl if not p.is_file()]
    if missing:
        raise SystemExit('missing RTL: %s' % missing)
    return rtl


def run_simulation(n_vectors: int) -> list:
    """One Verilator build (via run_sim.run_case, vector 0) + one process
    per remaining vector reusing the same executable through plusargs."""
    for i in range(n_vectors):
        (PROBE_BUILD / VECTOR_ORDER[i]).mkdir(parents=True, exist_ok=True)

    case = sim.Case(name=CASE_NAME, tb='experiments/npu_probe/tb_npu_probe.sv',
                    rtl=[str(p) for p in rtl_file_list()], timeout=600)
    verilator, _ = sim._toolchain()
    sim.ensure_runtime(verilator, print)
    args = argparse.Namespace(clean=False, trace=False, verbose=False)
    print('building + running vector 0 (%s) ...' % VECTOR_ORDER[0])
    result = sim.run_case(case, verilator, args)
    print(result.output)
    print('vector 0: ok=%s log=%s' % (result.ok, result.log_path))
    if not result.ok:
        raise SystemExit('vector 0 simulation failed: %s' % result.detail)

    runs = [{'name': VECTOR_ORDER[0], 'output': result.output,
             'seconds': result.seconds}]
    for i in range(1, n_vectors):
        name = VECTOR_ORDER[i]
        outdir = 'build/sim/npu_probe/%s' % name
        (PROBE_BUILD / name).mkdir(parents=True, exist_ok=True)
        print('running vector %d (%s) ...' % (i, name))
        t0 = time.time()
        run = subprocess.run([str(EXE_PATH), '+vec=%d' % i, '+outdir=%s' % outdir],
                             cwd=str(ROOT), env=sim._build_env(),
                             capture_output=True, text=True, encoding='utf-8',
                             errors='replace', timeout=600)
        output = (run.stdout or '') + (run.stderr or '')
        print(output)
        if run.returncode != 0 or 'RESULT: PASS' not in output:
            raise SystemExit('vector %d (%s) simulation failed' % (i, name))
        runs.append({'name': name, 'output': output,
                     'seconds': time.time() - t0})
    return runs


def extract_cycles(output: str) -> int:
    m = re.search(r'cycles=(\d+)', output)
    if not m:
        raise SystemExit('no cycle count in simulation output')
    return int(m.group(1))


def collect_snapshots(vec: dict) -> dict:
    """Read RTL hex dumps, write .bin snapshots, return stats + arrays."""
    outdir = PROBE_BUILD / vec['name']
    layers = {}
    arrays = {}
    for bin_name, hex_name, count, ctype in LAYER_SPECS:
        vals = read_hex(outdir / (hex_name + '.hex'))
        if len(vals) != count:
            raise SystemExit('%s/%s: expected %d values, got %d'
                             % (vec['name'], hex_name, count, len(vals)))
        if ctype == 's32':
            arr = np.asarray(vals, np.uint32).view(np.int32).astype(np.int64)
            raw = np.asarray(vals, np.uint32).view(np.int32).astype(np.int32)
        elif ctype == 'u16':
            arr = np.asarray(vals, np.int64)
            raw = np.asarray(vals, np.uint16)
        else:
            arr = np.asarray(vals, np.int64)
            raw = np.asarray(vals, np.uint8)
        bin_path = outdir / (bin_name + ('_s32.bin' if ctype == 's32' else
                                         '_u16.bin' if ctype == 'u16' else '_u8.bin'))
        raw.tofile(str(bin_path))
        layers[bin_name] = {
            'file': str(bin_path.relative_to(ROOT)).replace('\\', '/'),
            'sha256': _sha256_file(bin_path),
            'container': ctype,
            **layer_stats(arr),
        }
        arrays[bin_name] = arr
    return {'layers': layers, 'arrays': arrays}


def compare_to_golden(arrays: dict, res: dict) -> dict:
    """RTL snapshots vs golden_pipeline.npu_forward, element-wise."""
    match = {}
    for bin_name, _, _, _ in LAYER_SPECS:
        gold = golden_stream(bin_name if bin_name != 'probs_q16' else 'probs_q16',
                             res) if bin_name != 'probs_q16' else golden_stream('probs_q16', res)
        rtl = arrays[bin_name]
        if gold.size != rtl.size:
            raise SystemExit('%s: golden size %d != rtl size %d'
                             % (bin_name, gold.size, rtl.size))
        diff = np.abs(rtl - gold)
        match[bin_name] = {
            'max_lsb': int(diff.max()),
            'n_diff': int((diff > 0).sum()),
            'identical': bool((diff == 0).all()),
        }
    logits_rtl = arrays['fc2'] - ZP_OUT_FC2
    logits_gold = np.asarray(res['logits'], np.int64)
    dl = np.abs(logits_rtl - logits_gold)
    match['logits'] = {
        'max_lsb': int(dl.max()),
        'n_diff': int((dl > 0).sum()),
        'identical': bool((dl == 0).all()),
    }
    match['all_identical'] = all(v['identical'] for k, v in match.items()
                                 if k != 'all_identical')
    return match, logits_rtl


def golden_ref_crosscheck(res: dict) -> dict:
    """sine440 only: golden recompute vs the committed golden_ref npy set."""
    out = {}
    for name in ('conv1', 'conv2', 'conv3', 'conv4', 'pool1', 'pool2', 'pool3',
                 'pool4', 'gap', 'fc1'):
        ref = np.load(GOLDEN_REF / (name + '.npy'))
        same = bool(np.array_equal(np.asarray(res[name]), ref))
        out[name] = {'identical': same}
    ref_f2 = np.load(GOLDEN_REF / 'fc2_logits.npy')
    out['fc2'] = {'identical': bool(np.array_equal(res['logits'], ref_f2))}
    ref_p = np.load(GOLDEN_REF / 'probs.npy')
    out['probs'] = {'identical': bool(np.array_equal(res['probs_q16'], ref_p))}
    out['all_identical'] = all(v['identical'] for v in out.values()
                               if isinstance(v, dict) and 'identical' in v)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--vectors', type=int, default=4,
                        help='number of probe vectors to run (1..4, order fixed)')
    parser.add_argument('--report', type=Path, default=REPORT_PATH,
                        help='output JSON report path')
    args = parser.parse_args(argv)
    n_vectors = max(1, min(args.vectors, 4))

    wall0 = time.time()
    vectors = build_vectors()
    vectors = vectors[:n_vectors]

    contract = golden.load_layer_contract()
    tables = golden.load_mel_tables()
    fc2_rec = {rec['name']: rec for rec in contract['layers']}['fc2']
    s_out = float(fc2_rec['s_out'])

    write_assets(vectors)

    goldens = {}
    t0 = time.time()
    for vec in vectors:
        res = golden.npu_forward(vec['feat'], contract, tables['exp_lut'])
        goldens[vec['name']] = res
    print('golden npu_forward (%d vectors): %.1f s' % (len(vectors), time.time() - t0))

    runs = run_simulation(n_vectors)
    cycles_by_name = {r['name']: extract_cycles(r['output']) for r in runs}
    seconds_by_name = {r['name']: r['seconds'] for r in runs}

    report_vectors = []
    for vec in vectors:
        name = vec['name']
        snap = collect_snapshots(vec)
        match, logits_rtl = compare_to_golden(snap['arrays'], goldens[name])
        probs_q16_rtl = snap['arrays']['probs_q16']
        probs_float = [int(v) / 65536.0 for v in probs_q16_rtl]
        percent = [int(round(p * 100.0)) for p in probs_float]

        # feat snapshot: the injection source of truth for this vector
        feat_bin = PROBE_BUILD / name / 'feat_u8.bin'
        vec['feat'].tofile(str(feat_bin))

        rec = {
            'name': name,
            'kind': vec['kind'],
            'source': vec['source'],
            'feat': {
                'file': str(feat_bin.relative_to(ROOT)).replace('\\', '/'),
                'sha256': _sha256_file(feat_bin),
                'shape': [64, 258], 'dtype': 'uint8', 'zp_in': 49,
                **layer_stats(vec['feat'].astype(np.int64)),
            },
            'cycles': cycles_by_name[name],
            'sim_seconds': round(seconds_by_name[name], 1),
            'top1_rtl': int(np.argmax(probs_q16_rtl)),
            'top1_golden': int(goldens[name]['top1']),
            'logits_int32_rtl': [int(v) for v in logits_rtl],
            'logits_int32_golden': [int(v) for v in goldens[name]['logits']],
            'logits_dequant_rtl': [float(v) * s_out for v in logits_rtl],
            'probs_q16_rtl': [int(v) for v in probs_q16_rtl],
            'probs_q16_golden': [int(v) for v in goldens[name]['probs_q16']],
            'probs_float_rtl': probs_float,
            'percent_rtl': percent,
            'layers': snap['layers'],
            'golden_match': match,
        }
        if name == 'sine440':
            rec['golden_ref_crosscheck'] = golden_ref_crosscheck(goldens[name])
        report_vectors.append(rec)

    total_cycles = sum(r['cycles'] for r in report_vectors)
    all_ident = all(r['golden_match']['all_identical'] for r in report_vectors)
    report = {
        'report': 'npu_probe_baseline_20261104',
        'date': '2026-11-04',
        'purpose': ('M0 localizable baseline: fixed feature vectors driven '
                    'through the full native NPU chain with per-layer numeric '
                    'snapshots; first board-side comparison judge is '
                    'logits_int32_rtl / probs_q16_rtl of each vector, layer '
                    'walk-back via conv/pool/gap snapshots'),
        'golden_truth': ('scripts/golden_pipeline.py bit-level path only; '
                         'torch is never used (fbgemm tile noise 21..67 LSB)'),
        'rtl_set': ('identical to sim/experiments/npu_full_native (npu_full_end '
                    'candidates + native DDR plumbing); production src/ untouched'),
        'input_assets': {
            'weights_image': {
                'path': 'scripts/outputs/weights_image.bin',
                'sha256': _sha256_file(ROOT / 'scripts/outputs/weights_image.bin')},
            'layer_contract': {
                'path': 'scripts/outputs/layer_contract.json',
                'sha256': _sha256_file(ROOT / 'scripts/outputs/layer_contract.json')},
            'mel_tables': {
                'path': 'scripts/outputs/mel_tables.json',
                'sha256': _sha256_file(ROOT / 'scripts/outputs/mel_tables.json')},
        },
        'layouts': {
            'feat_u8.bin': ('(64,258) row-major mel-major: offset = mel*258 + '
                            'frame; uint8 quint8 domain, zp_in = 49'),
            'conv/pool snapshots': ('RTL output stream order (row, group, col, '
                                    'lane): offset = ((row*(C/16) + group)*W + '
                                    'col)*16 + lane; uint8 container'),
            'gap_s32.bin': '256 x int32 little-endian, channel order',
            'fc1_u8.bin': '128 x uint8 (ReLU rail domain, zp_out = 0)',
            'fc2_u8.bin': '8 x uint8 container values (zp_out = 57)',
            'logits_int32_rtl': 'fc2_u8 - 57 per element (s8 domain)',
            'probs_q16.bin': '8 x uint16 little-endian Q0.16',
            'sha256_semantics': 'sha256 of the raw .bin byte content',
        },
        'vectors': report_vectors,
        'summary': {
            'vectors_run': len(report_vectors),
            'vector_order': VECTOR_ORDER[:len(report_vectors)],
            'total_cycles': total_cycles,
            'total_sim_seconds': round(sum(seconds_by_name.values()), 1),
            'total_wall_seconds': round(time.time() - wall0, 1),
            'all_layers_identical_all_vectors': all_ident,
            'other_class_samples': ('none available: reports/golden_ref/ holds '
                                    'only sine_440_full and tests/fixtures/ only '
                                    'sine variants + silence; recorded as-is. '
                                    'v3 sine_440_twolevel added as an additional '
                                    'real mel variant, not a different class'),
            'determinism': ('feat vectors fixed by seed/fixture; RTL dumps are '
                            'functions of (weights_image, feat) only; rerun '
                            'reproduces identical sha256 per layer'),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, 'w', encoding='ascii', newline='\n') as fh:
        json.dump(report, fh, indent=2)
        fh.write('\n')
    print('report written: %s' % args.report)
    print('all layers identical across all vectors: %s' % all_ident)
    return 0 if all_ident else 1


if __name__ == '__main__':
    raise SystemExit(main())
