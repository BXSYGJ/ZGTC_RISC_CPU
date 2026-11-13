"""Restore a populated modified copy and execute the original CPU regression."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    subprocess.run([sys.executable, str(HERE / 'capture_baseline.py')], check=True)
    manifest = json.loads((HERE / 'BASELINE_MANIFEST.json').read_text(encoding='utf-8'))
    baseline = ROOT / 'build/pacerv_shared_system/baseline/source'
    out = ROOT / 'build/pacerv_shared_system/integration_rollback'
    target = out / 'restored_copy'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'ROLLBACK_TEST_COPY.json').write_text(json.dumps({'purpose': 'isolated rollback regression'}) + '\n')
    live_before = {item['path']: digest(REPO / item['path']) for item in manifest['files']}
    for item in manifest['files']:
        destination = target / item['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / item['path'], destination)
    wrapper = 'instrec_fpga/src/cpu/rv32_cpu_subsys.sv'
    if digest(target / wrapper) == next(x['sha256'] for x in manifest['files'] if x['path'] == wrapper):
        raise RuntimeError('Rollback test must begin with the modified wrapper')
    def ps_literal(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"
    shell_command = ("& ([scriptblock]::Create([System.IO.File]::ReadAllText("
                     + ps_literal(HERE / 'ROLLBACK.sh') + "))) -BaselineDirectory "
                     + ps_literal(baseline) + ' -TargetDirectory ' + ps_literal(target)
                     + ' -EvidenceDirectory ' + ps_literal(HERE))
    commands = [['pwsh', '-NoProfile', '-Command', shell_command]]
    sources = [target / 'instrec_fpga/sim/tb_rv_cpu.sv', target / wrapper]
    sources += [target / 'cpu/rtl' / f'rv32_{name}.sv' for name in
                ('core', 'alu', 'decode', 'muldiv', 'btb', 'machine')]
    commands += [[shutil.which('iverilog'), '-g2012', '-s', 'tb_rv_cpu',
                  '-o', str(out / 'original.vvp'), *map(str, sources)],
                 [shutil.which('vvp'), '-i', str(out / 'original.vvp')]]
    report = {'baseline_commit': manifest['baseline_commit'], 'commands': [], 'passed': False}
    try:
        for command in commands:
            run = subprocess.run(command, cwd=target / 'instrec_fpga', capture_output=True, timeout=180)
            output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
            report['commands'].append({'command': command, 'cwd': str(target / 'instrec_fpga'),
                                       'exit_status': run.returncode, 'output': output})
            print(output, end='')
            if run.returncode:
                raise RuntimeError('Integration rollback failed')
        report['all_original_hashes_restored'] = all(digest(target / x['path']) == x['sha256'] for x in manifest['files'])
        report['live_modified_files_unchanged'] = all(digest(REPO / path) == sha for path, sha in live_before.items())
        report['passed'] = (report['all_original_hashes_restored'] and report['live_modified_files_unchanged']
                            and 'RESULT: PASS' in output and 'cycles=460012 inst=180008 acc=0xf2d8888b' in output)
    finally:
        (HERE / 'evidence/INTEGRATION_ROLLBACK_RESULTS.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise RuntimeError('Original behavior was not restored')
    print(f'INTEGRATION_ROLLBACK_PASS files={len(manifest["files"])} cycles=460012 retired=180008 live_modified_unchanged=1')


if __name__ == '__main__':
    main()
