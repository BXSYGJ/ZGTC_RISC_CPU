"""Verify the reference counter and all serialized clock-probe characters."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'build/pacerv_shared_system/clock_probe_sim'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sources = [HERE / 'tests/tb_clock_probe.v', HERE / 'pg200_clock_probe.v',
               ROOT / 'src/ctrl/uart_tx.v']
    commands = [[shutil.which('iverilog') or 'D:/AAAPP/iverilog/bin/iverilog.exe',
                 '-g2012', '-s', 'tb_clock_probe', '-o', str(OUT / 'test.vvp'),
                 *map(str, sources)],
                [shutil.which('vvp') or 'D:/AAAPP/iverilog/bin/vvp.exe', str(OUT / 'test.vvp')]]
    report = {'inputs': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in sources], 'commands': [], 'passed': False}
    try:
        for command in commands:
            run = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=30)
            output = run.stdout + run.stderr
            report['commands'].append({'command': command, 'cwd': str(OUT),
                                       'exit_status': run.returncode, 'output': output})
            print(output, end='')
            if run.returncode:
                raise RuntimeError('Clock probe simulation failed')
        if 'CLOCK_PROBE_SIM PASS' not in output:
            raise RuntimeError('Clock probe did not complete')
        report['passed'] = True
    finally:
        (OUT / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
