"""Check checksum pipelining and GAP storage with frozen originals and rollback."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = ('src/ctrl/weight_loader.v', 'src/npu/gap_unit.v')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError('Expected exactly one testbench insertion: ' + old)
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('BASELINE', 'MODIFIED', 'ROLLBACK'), required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--baseline-build', type=Path,
                        default=ROOT / 'build/pacerv_shared_system/pds/full-20261114-021145-full')
    args = parser.parse_args()
    if not args.label.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Use an alphanumeric study label')
    study = ROOT / 'build/pacerv_shared_system/timing_controls' / args.label
    out = study / args.mode
    out.mkdir(parents=True, exist_ok=False)
    before = {p: digest(ROOT / p) for p in FILES}
    manifest = json.loads((args.baseline_build / 'INPUTS.json').read_text(encoding='utf-8'))
    original_hashes = {p['path']: p['sha256'] for p in manifest['files']}
    for relative in FILES:
        source = (args.baseline_build / 'inputs' / relative
                  if args.mode == 'BASELINE' else ROOT / relative)
        if args.mode == 'BASELINE' and digest(source) != original_hashes[relative]:
            raise RuntimeError('Frozen baseline changed: ' + relative)
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if args.mode == 'ROLLBACK':
            original = study / 'BASELINE' / relative
            shutil.copy2(original, destination)
            if digest(destination) != original_hashes[relative]:
                raise RuntimeError('Rollback hash mismatch')
    spec = importlib.util.spec_from_file_location('loader_gap_sim', ROOT / 'sim/run_sim.py')
    sim = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = sim
    spec.loader.exec_module(sim)
    sim.prepare_weight_loader(out)
    loader_tb = (ROOT / 'sim/tb_weight_loader.sv').read_text(encoding='utf-8')
    loader_tb = replace_once(loader_tb, 'build/sim/weight_loader/payload.hex',
                            (out / 'payload.hex').as_posix())
    expected_hex = (out / 'digest.txt').read_text().strip()
    hex_checks = ' && '.join(f"rx_text[{8+i}] == 8'h{ord(c):02X}" for i, c in enumerate(expected_hex))
    loader_tb = replace_once(loader_tb, 'check("A weight_ok",',
        f'check("A all eight digest characters", {hex_checks});\n        check("A weight_ok",')
    corruption = '''reset_dut();
        acc0 = 0; acc1 = 0; acc2 = 0; acc3 = 0;
        send_frame(16'd0, 1'b0);
        wait_loader_idle();
        mem32[0] = mem32[0] ^ 32'd1;
        send_end_frame();
        wait_loader_idle();
        check("D changed DDR data detected", weight_err === 1'b1);
        check("D WERR reply retained", rx_len == 14 && rx_text[1] == 8'h57 &&
              rx_text[2] == 8'h45 && rx_text[3] == 8'h52 && rx_text[4] == 8'h52);
        '''
    loader_tb = replace_once(loader_tb, '$display("=== tb_weight_loader done:',
                            corruption + '$display("=== tb_weight_loader done:')
    (out / 'tb_weight_loader.sv').write_text(loader_tb, encoding='utf-8')
    shutil.copy2(HERE / 'tb_gap_storage.sv', out / 'tb_gap_storage.sv')
    tools = [shutil.which(name) for name in ('iverilog', 'vvp')]
    if not all(tools):
        raise RuntimeError('Native Icarus Verilog is required')
    report = {'mode': args.mode, 'inputs': [{'path': p, 'sha256': digest(out / p)} for p in FILES],
              'baseline_manifest': str(args.baseline_build / 'INPUTS.json'),
              'baseline_manifest_sha256': digest(args.baseline_build / 'INPUTS.json'),
              'test_inputs': [{'path': str(out / p), 'sha256': digest(out / p)} for p in
                              ('tb_weight_loader.sv', 'tb_gap_storage.sv', 'payload.hex')],
              'commands': [], 'passed': False}
    try:
        for name, top, rtl, marker in (
            ('loader', 'tb_weight_loader', FILES[0], 'RESULT: PASS tb_weight_loader'),
            ('gap', 'tb_gap_storage', FILES[1], 'GAP_STORAGE_PASS')):
            tb = out / ('tb_weight_loader.sv' if name == 'loader' else 'tb_gap_storage.sv')
            executable = out / (name + '.vvp')
            commands = [[tools[0], '-g2012', '-s', top, '-o', str(executable), str(tb), str(out / rtl)],
                        [tools[1], '-i', str(executable)]]
            for index, command in enumerate(commands):
                run = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=180)
                text = (run.stdout + run.stderr).decode('utf-8', errors='replace')
                log = out / f'{name}_{index}.log'
                log.write_text(text, encoding='utf-8')
                report['commands'].append({'command': command, 'cwd': str(ROOT),
                    'exit_status': run.returncode, 'output': text, 'log_sha256': digest(log)})
                if run.returncode or (index == 1 and marker not in text):
                    print(text)
                    raise RuntimeError('Timing control functional check failed: ' + name)
                if index == 1:
                    print('\n'.join(line for line in text.splitlines()
                                    if 'PASS' in line or 'done:' in line))
        report['live_sources_unchanged'] = all(digest(ROOT / p) == h for p, h in before.items())
        report['passed'] = report['live_sources_unchanged']
    finally:
        (out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if not report['passed']:
        raise RuntimeError('Source changed during functional validation')
    print(f'LOADER_GAP_{args.mode}_PASS checksum_corruption=1 gap_outputs=768 live_unchanged=1')


if __name__ == '__main__':
    main()
