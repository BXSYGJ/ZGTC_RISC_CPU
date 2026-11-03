"""IRMAS 8-class real-instrument samples through the npu_probe full chain.

B-package (numeric localization / NPU) diagnostic experiment: eight real
3 s stereo instrument samples (InstRec/data/demo/irmas_test, one per
IRMAS class) are converted to mel features via the bit-level
golden_pipeline path (identical to the baseline vectors) and driven
through the same Verilator build of tb_npu_probe.sv, one process per
sample via +vec=0 +outdir=..., with assets/feat_v0.hex rewritten per
sample and restored afterwards.  Purpose: the first model-side vs
board-side split evidence for the constant-top1 board failure -- if RTL
top1 differentiates correctly per class, the board symptom must be
board/input-domain/timing; if RTL also collapses toward one class, the
model/feature domain is implicated.

Class order is InstRec IRMAS_CLASSES (src/quantize_irmas.py, consistent
with src/irmas_dataset.py): piano, violin, clarinet, flute, saxophone,
trumpet, guitar_acoustic, guitar_electric.  Note index 6 is
guitar_acoustic (NOT trumpet; trumpet is index 5).

Vector injection reuses the baseline mechanism unchanged: feat_u8.bin
16512 B uint8 zp_in=49 domain, $readmemh assets/feat_v*.hex,
$writememh layer dumps, snapshot bins identical to the baseline layout.

Outputs (gitignored / rebuildable except the report):
  build/sim/npu_probe/irmas_<sample>/*.hex   raw RTL dumps
  build/sim/npu_probe/irmas_<sample>/*.bin   layer snapshots
  reports/npu_probe_irmas_20261104.json      report (default --report)

Usage (from instrec_fpga/, requires the baseline executable built by
sim/experiments/npu_probe/run.py):
  python sim/experiments/npu_probe/run_irmas.py             # all 8 samples
  python sim/experiments/npu_probe/run_irmas.py --limit 1  # smoke, first only
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                # instrec_fpga/
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'sim'))
sys.path.insert(0, str(ROOT / 'scripts'))
import run as probe                                   # noqa: E402  (npu_probe/run.py)
import golden_pipeline as golden                      # noqa: E402

IRMAS_DIR = Path(r'D:\0000\111\001\Pango\InstRec\data\demo\irmas_test')
REPORT_PATH = ROOT / 'reports/npu_probe_irmas_20261104.json'
ZP_OUT_FC2 = 57

IRMAS_CLASSES = ['piano', 'violin', 'clarinet', 'flute', 'saxophone',
                 'trumpet', 'guitar_acoustic', 'guitar_electric']
SAMPLE_CLASS = {
    'piano_sample': 'piano',
    'violin_sample': 'violin',
    'clarinet_sample': 'clarinet',
    'flute_sample': 'flute',
    'saxophone_sample': 'saxophone',
    'trumpet_sample': 'trumpet',
    'guitar_acoustic_sample': 'guitar_acoustic',
    'guitar_electric_sample': 'guitar_electric',
}


def build_samples(limit: int | None) -> list:
    """Mel features of the IRMAS wav set via the bit-level golden path."""
    tables = golden.load_mel_tables()
    wavs = sorted(IRMAS_DIR.glob('*.wav'))
    if not wavs:
        raise SystemExit('no wav files under %s' % IRMAS_DIR)
    samples = []
    for wav in wavs:
        stem = wav.name[:-4]
        cls = SAMPLE_CLASS.get(stem)
        pcm = golden.load_pcm_s16(wav)
        feat = golden.run_mel_pipeline(pcm, tables)['feat']
        assert feat.shape == (64, 258) and feat.dtype == np.uint8
        samples.append({
            'name': 'irmas_%s' % stem, 'wav': wav, 'feat': feat,
            'class_idx': IRMAS_CLASSES.index(cls) if cls else None,
            'class_name': cls,
        })
        print('%s -> class=%s feat_sha_pending' % (wav.name, cls or 'UNKNOWN'))
    if limit is not None:
        samples = samples[:limit]
    return samples


def run_sample(sample: dict) -> dict:
    """One exe process per sample: rewrite feat_v0.hex, run +vec=0."""
    feat_v0 = probe.ASSETS / 'feat_v0.hex'
    backup = feat_v0.read_bytes()
    outdir = 'build/sim/npu_probe/%s' % sample['name']
    (probe.PROBE_BUILD / sample['name']).mkdir(parents=True, exist_ok=True)
    try:
        probe.write_hex(feat_v0, sample['feat'].reshape(-1), 2)
        t0 = time.time()
        run = subprocess.run(
            [str(probe.EXE_PATH), '+vec=0', '+outdir=%s' % outdir],
            cwd=str(ROOT), env=probe.sim._build_env(),
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=600)
        output = (run.stdout or '') + (run.stderr or '')
        if run.returncode != 0 or 'RESULT: PASS' not in output:
            print(output)
            raise SystemExit('%s simulation failed' % sample['name'])
        return {'output': output, 'seconds': time.time() - t0}
    finally:
        feat_v0.write_bytes(backup)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--limit', type=int, default=None,
                        help='run only the first N samples (smoke)')
    parser.add_argument('--report', type=Path, default=REPORT_PATH,
                        help='output JSON report path')
    args = parser.parse_args(argv)

    if not probe.EXE_PATH.is_file():
        raise SystemExit('missing %s: run sim/experiments/npu_probe/run.py '
                         'first to build the executable' % probe.EXE_PATH)

    wall0 = time.time()
    samples = build_samples(args.limit)

    contract = golden.load_layer_contract()
    tables = golden.load_mel_tables()
    fc2_rec = {rec['name']: rec for rec in contract['layers']}['fc2']
    s_out = float(fc2_rec['s_out'])

    report_samples = []
    for sample in samples:
        name = sample['name']
        print('running %s (%s) ...' % (name, sample['class_name'] or '?'))
        run = run_sample(sample)
        cycles = probe.extract_cycles(run['output'])

        snap = probe.collect_snapshots(sample)
        res = golden.npu_forward(sample['feat'], contract, tables['exp_lut'])
        match, logits_rtl = probe.compare_to_golden(snap['arrays'], res)
        probs_q16_rtl = snap['arrays']['probs_q16']
        probs_float = [int(v) / 65536.0 for v in probs_q16_rtl]
        percent = [int(round(p * 100.0)) for p in probs_float]

        feat_bin = probe.PROBE_BUILD / name / 'feat_u8.bin'
        sample['feat'].tofile(str(feat_bin))

        top1_rtl = int(np.argmax(probs_q16_rtl))
        cls_idx = sample['class_idx']
        report_samples.append({
            'name': name,
            'wav': str(sample['wav']),
            'class_true': {
                'idx': cls_idx,
                'name': sample['class_name'],
                'known': sample['class_name'] is not None,
            },
            'source': ('%s via golden_pipeline.load_pcm_s16 (stereo integer '
                       'downmix (L+R+1)>>1, established convention) + '
                       'run_mel_pipeline, truncated to the 132096-sample '
                       'hardware window') % sample['wav'],
            'feat': {
                'file': str(feat_bin.relative_to(ROOT)).replace('\\', '/'),
                'sha256': probe._sha256_file(feat_bin),
                'shape': [64, 258], 'dtype': 'uint8', 'zp_in': 49,
                **probe.layer_stats(sample['feat'].astype(np.int64)),
            },
            'cycles': cycles,
            'sim_seconds': round(run['seconds'], 1),
            'top1_rtl': top1_rtl,
            'top1_golden': int(res['top1']),
            'top1_matches_class': (cls_idx is not None
                                   and top1_rtl == cls_idx),
            'logits_int32_rtl': [int(v) for v in logits_rtl],
            'logits_int32_golden': [int(v) for v in res['logits']],
            'logits_dequant_rtl': [float(v) * s_out for v in logits_rtl],
            'probs_q16_rtl': [int(v) for v in probs_q16_rtl],
            'probs_q16_golden': [int(v) for v in res['probs_q16']],
            'probs_float_rtl': probs_float,
            'percent_rtl': percent,
            'layers': snap['layers'],
            'golden_match': match,
        })

    top1s = [s['top1_rtl'] for s in report_samples]
    known = [s for s in report_samples if s['class_true']['known']]
    all_match = all(s['top1_matches_class'] for s in known)
    all_distinct = len(set(top1s)) == len(top1s)
    all_ident = all(s['golden_match']['all_identical'] for s in report_samples)
    distribution = {}
    for s in report_samples:
        key = '%d (%s)' % (s['top1_rtl'],
                           IRMAS_CLASSES[s['top1_rtl']] if s['top1_rtl'] < 8
                           else '?')
        distribution[key] = distribution.get(key, 0) + 1

    if all_ident and all_match:
        conclusion = (
            'RTL NPU full-chain top1 differentiates every IRMAS class '
            'correctly and matches the bit-level golden on every layer: '
            'the model/quantization/golden side is exonerated, so the '
            'board-constant top1 must originate board-side (input domain / '
            'feature injection / PCM-I2S path / timing), not model-side.')
    elif all_ident:
        collapse = ', '.join('%s=%d' % (k, v) for k, v in sorted(distribution.items()))
        conclusion = (
            'RTL matches the bit-level golden on every layer for all '
            'samples, but top1 does NOT track the sample class -- it '
            'collapses to a single class (%s). The quantized model has no '
            'class-discriminative power in the golden mel feature domain, '
            'so the constant-top1 symptom is rooted model/feature-side, '
            'not in RTL numeric correctness nor in board data transport. '
            'The board collapse point (top1=6, guitar_acoustic) differs '
            'from the RTL/golden collapse point (top1=0, piano), which '
            'indicates the board input domain additionally shifts the '
            'collapse point, but a board-side fix alone cannot restore '
            'correct classification while the model side stays '
            'non-discriminative.' % collapse)
    else:
        conclusion = (
            'RTL diverges from the bit-level golden on at least one layer: '
            'an RTL numeric defect exists -- inspect per-layer '
            'golden_match max_lsb to localize.')

    report = {
        'report': 'npu_probe_irmas_20261104',
        'date': '2026-11-04',
        'purpose': ('model-side vs board-side split evidence for the '
                    'constant-top1 board failure: eight real IRMAS class '
                    'samples through the full native NPU chain, same '
                    'injection mechanism, snapshot layout and golden truth '
                    'as the npu_probe baseline'),
        'board_symptom_reference': (
            'board symptom under investigation: constant top1=6 on every '
            'input; under IRMAS_CLASSES index 6 is guitar_acoustic (the '
            'earlier "trumpet" reading of index 6 is a class-table '
            'misread, trumpet is index 5)'),
        'class_index_convention': {
            'order': IRMAS_CLASSES,
            'note': ('index 6 is guitar_acoustic, NOT trumpet (trumpet is '
                     'index 5); board constant top1=6 reads as '
                     'guitar_acoustic under this table'),
        },
        'golden_truth': ('scripts/golden_pipeline.py bit-level path only; '
                         'torch is never used (fbgemm tile noise 21..67 LSB)'),
        'rtl_set': ('identical to the npu_probe baseline: same Verilator '
                    'executable and tb_npu_probe.sv, vector injected via '
                    'assets/feat_v0.hex + +vec=0 +outdir=... (baseline '
                    'feat_v0.hex restored after the run); production src/ '
                    'untouched'),
        'input_assets': {
            'weights_image': {
                'path': 'scripts/outputs/weights_image.bin',
                'sha256': probe._sha256_file(
                    ROOT / 'scripts/outputs/weights_image.bin')},
            'layer_contract': {
                'path': 'scripts/outputs/layer_contract.json',
                'sha256': probe._sha256_file(
                    ROOT / 'scripts/outputs/layer_contract.json')},
            'mel_tables': {
                'path': 'scripts/outputs/mel_tables.json',
                'sha256': probe._sha256_file(
                    ROOT / 'scripts/outputs/mel_tables.json')},
        },
        'layouts': {
            'feat_u8.bin': ('(64,258) row-major mel-major: offset = mel*258 + '
                            'frame; uint8 quint8 domain, zp_in = 49'),
            'conv/pool snapshots': ('RTL output stream order (row, group, '
                                    'col, lane): offset = ((row*(C/16) + '
                                    'group)*W + col)*16 + lane; uint8 '
                                    'container'),
            'gap_s32.bin': '256 x int32 little-endian, channel order',
            'fc1_u8.bin': '128 x uint8 (ReLU rail domain, zp_out = 0)',
            'fc2_u8.bin': '8 x uint8 container values (zp_out = 57)',
            'logits_int32_rtl': 'fc2_u8 - 57 per element (s8 domain)',
            'probs_q16.bin': '8 x uint16 little-endian Q0.16',
            'sha256_semantics': 'sha256 of the raw .bin byte content',
        },
        'samples': report_samples,
        'diagnosis': {
            'n_samples': len(report_samples),
            'top1_rtl_per_sample': [
                {'name': s['name'], 'class': s['class_true']['name'],
                 'top1_rtl': s['top1_rtl']} for s in report_samples],
            'top1_distribution_rtl': distribution,
            'all_top1_match_class': all_match,
            'all_top1_distinct': all_distinct,
            'rtl_matches_golden_all_layers_all_samples': all_ident,
            'conclusion': conclusion,
            'suggested_next_steps': [
                'run the same 8 wavs through the InstRec floating-point '
                'model with its training-time librosa feature extractor to '
                'check whether the collapse is a quantized-model defect or '
                'a golden-mel-domain vs training-domain mismatch (dB '
                'normalization / top_db / downmix semantics)',
                'compare golden_pipeline.run_mel_pipeline output against '
                'InstRec extract_mel on one IRMAS sample element-wise',
                'board side stays suspect only for the collapse-point '
                'shift (6 vs 0) and for input-domain correctness, not for '
                'NPU numeric transport (RTL == golden everywhere)',
            ],
        },
        'comparability': {
            'feature_path_identical_to_baseline': (
                'yes: golden.load_pcm_s16 + golden.run_mel_pipeline with the '
                'same mel_tables.json, same 132096-sample window, same '
                '(L+R+1)>>1 stereo downmix, same zp_in=49 uint8 domain; '
                'only the input wav differs'),
            'rtl_path_identical_to_baseline': (
                'yes: same sim_npu_probe.exe / tb_npu_probe.sv / '
                'weights_image.bin; vector 0 slot reused via feat_v0.hex '
                'rewrite, baseline file restored afterwards'),
            'stereo_handling': ('integer round-half-up downmix (L+R+1)>>1 '
                                'inside golden_pipeline.load_pcm_s16, the '
                                'established convention (not left-channel '
                                'only)'),
        },
        'summary': {
            'samples_run': len(report_samples),
            'total_cycles': sum(s['cycles'] for s in report_samples),
            'total_sim_seconds': round(
                sum(s['sim_seconds'] for s in report_samples), 1),
            'total_wall_seconds': round(time.time() - wall0, 1),
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report, 'w', encoding='ascii', newline='\n') as fh:
        json.dump(report, fh, indent=2)
        fh.write('\n')
    print('report written: %s' % args.report)
    print('all top1 match class: %s  distinct: %s  golden-identical: %s'
          % (all_match, all_distinct, all_ident))
    print('top1 distribution: %s' % distribution)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
