"""Exercise the production registered activation mux under downstream stalls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    out = ROOT / 'build/pacerv_shared_system/activation_mux'
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'sim/experiments/activation_store/tb_activation_store_mux.sv',
               ROOT / 'src/npu/activation_store_mux.v']
    executable = out / 'mux.vvp'
    report = {'passed': False, 'inputs': [{'path': p.relative_to(ROOT).as_posix(),
               'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources], 'commands': []}
    try:
        for command in ([shutil.which('iverilog'), '-g2012', '-s', 'tb_activation_store_mux',
                         '-o', str(executable), *map(str, sources)], [shutil.which('vvp'), str(executable)]):
            run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
            output = (run.stdout + run.stderr).decode('utf-8', errors='replace')
            report['commands'].append({'command': command, 'exit_status': run.returncode, 'output': output})
            print(output, end='')
            if run.returncode:
                raise RuntimeError('Production activation mux simulation failed')
        report['passed'] = 'RESULT: PASS activation store mux: 24 transactions, mixed immediate/delayed R' in output
    finally:
        (out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise RuntimeError('Activation mux checks incomplete')
    print('ACTIVATION_MUX_PASS transactions=24 writes=12 reads=12')


if __name__ == '__main__':
    main()
