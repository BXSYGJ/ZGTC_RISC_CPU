"""Compare all five dashboard rasters before and after the font pipeline split."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASELINE = '852f067db4a4a710f5355e3ab311f035ced5b48d'
FILES = ('sim/tb_dashboard_ui.sv', 'src/ui/dashboard_renderer.v', 'src/ui/dashboard_text.v')
FRAMES = ('waiting', 'ready', 'full_scale', 'zero', 'clamped')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-cache', type=Path)
    parser.add_argument('--run-label', default='')
    args = parser.parse_args()
    if args.run_label and not all(c.isalnum() or c in '_-' for c in args.run_label):
        parser.error('Run label accepts letters, digits, underscores and hyphens')
    suffix = '_' + args.run_label if args.run_label else ''
    out = ROOT / ('build/pacerv_shared_system/dashboard_equivalence_7clock' + suffix)
    out.mkdir(parents=True, exist_ok=True)
    report = {'baseline_commit': BASELINE, 'commands': [], 'inputs': [], 'passed': False}
    for relative in FILES:
        path = ROOT / relative
        report['inputs'].append({'path': relative, 'sha256': digest(path)})
    for path in sorted((ROOT / 'src/ui').glob('dashboard_*.hex')):
        report['inputs'].append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path)})
    frames = {}
    try:
        for label in ('baseline', 'modified'):
            if label == 'baseline' and args.baseline_cache:
                cache = args.baseline_cache.resolve(strict=True)
                cached_report = json.loads((cache.parent / 'RESULT.json').read_text(encoding='utf-8'))
                commands = [c for c in cached_report['commands'] if c['label'] == 'baseline']
                if (cached_report['baseline_commit'] != BASELINE or len(commands) != 2
                        or any(c['exit_status'] != 0 for c in commands)
                        or 'RESULT: PASS dashboard_ui frames=5 active_pixels=10368000 bar_checks=2000'
                        not in commands[-1]['output']):
                    raise RuntimeError('Cached baseline did not complete the five-frame test')
                for relative in FILES:
                    original = subprocess.check_output(['git', 'show', BASELINE + ':instrec_fpga/' + relative],
                                                       cwd=ROOT.parent)
                    if relative.endswith('tb_dashboard_ui.sv'):
                        original = original.replace(b'build/sim/dashboard_ui/', (cache.as_posix() + '/').encode())
                    if (cache / Path(relative).name).read_bytes() != original:
                        raise RuntimeError('Cached baseline source differs: ' + relative)
                for item in cached_report['inputs']:
                    if item['path'].endswith('.hex') and digest(ROOT / item['path']) != item['sha256']:
                        raise RuntimeError('Cached baseline ROM changed: ' + item['path'])
                frames[label] = {name: digest(cache / (name + '.ppm')) for name in FRAMES}
                if any((cache / (name + '.ppm')).stat().st_size != 6220817 for name in FRAMES):
                    raise RuntimeError('Cached baseline frame is incomplete')
                report['commands'].extend(commands)
                report['cached_baseline'] = {'directory': str(cache),
                    'report_sha256': digest(cache.parent / 'RESULT.json'), 'frames': frames[label]}
                print('DASHBOARD_BASELINE_CACHE_PASS frames=5 source_and_rom_hashes=exact', flush=True)
                continue
            directory = out / label
            directory.mkdir(parents=True, exist_ok=True)
            sources = []
            for relative in FILES:
                original = (subprocess.check_output(['git', 'show', BASELINE + ':instrec_fpga/' + relative],
                                                    cwd=ROOT.parent)
                            if label == 'baseline' else (ROOT / relative).read_bytes())
                destination = directory / Path(relative).name
                if relative.endswith('tb_dashboard_ui.sv'):
                    original = original.replace(b'build/sim/dashboard_ui/', (directory.as_posix() + '/').encode())
                destination.write_bytes(original)
                sources.append(destination)
            executable = directory / 'dashboard.vvp'
            commands = [[shutil.which('iverilog'), '-g2012', '-s', 'tb_dashboard_ui', '-o', str(executable),
                         *map(str, sources)], [shutil.which('vvp'), '-i', str(executable)]]
            for command in commands:
                run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=1200)
                output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
                report['commands'].append({'label': label, 'command': command, 'exit_status': run.returncode,
                                           'output': output})
                print(output, end='', flush=True)
                if run.returncode:
                    raise RuntimeError(label + ' dashboard simulation failed')
            if 'RESULT: PASS dashboard_ui frames=5 active_pixels=10368000 bar_checks=2000' not in output:
                raise RuntimeError(label + ' dashboard checks incomplete')
            frames[label] = {name: digest(directory / (name + '.ppm')) for name in FRAMES}
        report['frames'] = frames
        report['all_five_rasters_identical'] = frames['baseline'] == frames['modified']
        report['passed'] = report['all_five_rasters_identical']
        if not report['passed']:
            raise RuntimeError('The pipeline split changed dashboard pixels')
    finally:
        (out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('DASHBOARD_EQUIVALENCE_PASS frames=5 pixels=10368000 bar_checks=2000 control_latency=7')


if __name__ == '__main__':
    main()
