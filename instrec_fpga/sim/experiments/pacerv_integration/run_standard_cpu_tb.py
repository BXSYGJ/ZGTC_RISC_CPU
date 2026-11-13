"""Run the repository's original CPU testbench with native Icarus Verilog."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from run_pacerv_checks import ROOT, run


def main() -> None:
    out = ROOT / 'build/pacerv_shared_system/standard_cpu_entry'
    out.mkdir(parents=True, exist_ok=True)
    iv, vvp = shutil.which('iverilog'), shutil.which('vvp')
    if not iv or not vvp:
        raise RuntimeError('Put native iverilog and vvp on PATH')
    sources = [ROOT / 'sim/tb_rv_cpu.sv', ROOT / 'src/cpu/rv32_cpu_subsys.sv',
               *sorted((ROOT / 'src/cpu/vendor/pacerv_h3').glob('*.sv'))]
    inputs = [*sources, ROOT / 'src/cpu/prog.hex']
    commands = [[iv, '-g2012', '-s', 'tb_rv_cpu', '-o', out / 'test.vvp', *sources],
                [vvp, '-i', out / 'test.vvp']]
    report = {'inputs': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                         for p in inputs], 'commands': [], 'passed': False}
    try:
        for command in commands:
            result = run(command, timeout=300)
            report['commands'].append(result)
            print(result['output'], end='')
            if result['exit_status']:
                raise RuntimeError('Standard CPU testbench failed')
        report['passed'] = 'RESULT: PASS' in report['commands'][-1]['output']
        if not report['passed']:
            raise RuntimeError('Missing CPU testbench completion')
    finally:
        (out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('STANDARD_CPU_TB_PASS')


if __name__ == '__main__':
    main()
