"""Compile and execute the isolated PaceRV wrapper integration regressions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VENDOR = ROOT / 'src/cpu/vendor/pacerv_h3'
OUT = ROOT / 'build/pacerv_integration'


def run(command, timeout=30):
    start = time.monotonic()
    result = subprocess.run([str(x) for x in command], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    return {'command': [str(x) for x in command], 'cwd': str(ROOT),
            'exit_status': result.returncode,
            'output': result.stdout + result.stderr,
            'elapsed_seconds': round(time.monotonic() - start, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true', help='omit the full audio-firmware run')
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    iv, vvp = shutil.which('iverilog'), shutil.which('vvp')
    if not iv or not vvp:
        raise RuntimeError('Install native Icarus Verilog and put iverilog/vvp on PATH')
    manifest = json.loads((VENDOR / 'PROVENANCE.json').read_text(encoding='utf-8-sig'))
    rtl = []
    for entry in manifest['files']:
        path = VENDOR / entry['file']
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.lower() != entry['sha256'].lower():
            raise RuntimeError(f'Frozen vendor source changed: {path}')
        rtl.append(path)
    wrapper = ROOT / 'src/cpu/rv32_cpu_subsys.sv'
    report = {'wrapper_sha256': hashlib.sha256(wrapper.read_bytes()).hexdigest(),
              'vendor_hashes_verified': len(rtl), 'results': [], 'passed': False}
    build = run([sys.executable, HERE / 'build_pacerv_directed.py'])
    report['results'].append(build)
    if build['exit_status']:
        raise RuntimeError(build['output'])
    cases = [('tb_pacerv_directed', 'PACERV_DIRECTED_PASS', 30),
             ('tb_pacerv_backpressure', 'PACERV_BACKPRESSURE_PASS', 30),
             ('tb_pacerv_fetch_fault', 'PACERV_FETCH_FAULT_PASS', 30)]
    if not args.quick:
        cases.append(('tb_pacerv_audio', 'RESULT: PASS', 300))
    try:
        for top, token, timeout in cases:
            target = OUT / f'{top}.vvp'
            comp = run([iv, '-g2012', '-s', top, '-o', target,
                        HERE / f'{top}.sv', wrapper, *rtl])
            report['results'].append(comp)
            if comp['exit_status']:
                raise RuntimeError(comp['output'])
            result = run([vvp, '-i', target], timeout=timeout)
            report['results'].append(result)
            (OUT / f'{top}.log').write_text(result['output'], encoding='utf-8')
            print(result['output'], end='')
            if result['exit_status'] or token not in result['output']:
                raise RuntimeError(f'{top} did not pass')
        report['passed'] = True
    finally:
        name = 'pacerv_checks_quick.json' if args.quick else 'pacerv_checks.json'
        (OUT / name).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PACERV_CHECKS_PASS cases={len(cases)} vendor_hashes={len(rtl)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
