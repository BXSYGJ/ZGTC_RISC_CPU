import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from load_use_profile import DRIVER_SHA256, file_hash, load_json, require
from run_load_use_profile import verified_build


def execute(build):
    manifest, _ = verified_build(build)
    require(manifest['SourceSnapshot']['sim/coremark_compiled.cpp'] == DRIVER_SHA256, 'Unexpected observer source')
    metadata = load_json(build / 'coremark.sim.uart.retire.json')
    start = f"{metadata['start_pc']:x}"
    stop = f"{metadata['stop_pc']:x}"
    cases = [('missing_start', None, stop, 'Missing trace boundary environment variable'),
             ('missing_stop', start, None, 'Missing trace boundary environment variable'),
             ('empty', '', stop, 'one to eight hex digits'),
             ('invalid_digit', 'xyz', stop, 'one to eight hex digits'),
             ('prefix', '0x' + start, stop, 'one to eight hex digits'),
             ('too_long', '100000000', stop, 'one to eight hex digits'),
             ('unaligned', f"{metadata['start_pc'] + 1:x}", stop, 'aligned RV32 address'),
             ('same', start, start, 'must be distinct'),
             ('wrong_start_csr', f"{metadata['start_pc'] - 4:x}", stop, 'invalid trace start boundary'),
             ('wrong_stop_csr', start, f"{metadata['stop_pc'] - 4:x}", 'invalid/duplicate stop boundary'),
             ('stop_before_start', stop, start, 'Missing start or invalid/duplicate stop boundary'),
             ('start_never_seen', 'fffffffc', stop, 'Missing start or invalid/duplicate stop boundary')]
    root = Path(__file__).resolve().parents[1]
    output = root / 'build' / 'load-use-observer-negative' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    output.mkdir(parents=True)
    results = []
    for name, start_value, stop_value, expected in cases:
        environment = os.environ.copy()
        for key, value in (('ZGTC_TRACE_START_PC', start_value), ('ZGTC_TRACE_STOP_PC', stop_value)):
            environment.pop(key, None)
            if value is not None:
                environment[key] = value
        uart = output / (name + '.uart')
        completed = subprocess.run([str(build / 'objects' / 'Vrv32_soc'), str(uart), '10000000'],
            cwd=build, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
        log = output / (name + '.log')
        log.write_text(completed.stdout, encoding='utf-8')
        require(completed.returncode == 1 and expected in completed.stdout, f'Negative control failed: {name}: {completed.stdout[-1000:]}')
        require(not Path(str(uart) + '.retire.json').exists(), 'Rejected run wrote success metadata')
        results.append(dict(name=name, expected=expected, returncode=completed.returncode, log_sha256=file_hash(log)))
    verified_build(build)
    report = dict(passed=True, build=str(build), manifest_sha256=file_hash(build / 'manifest.json'),
        script_sha256=file_hash(Path(__file__)), tests=results)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'PASS {len(results)} observer negative controls: {output}')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Reject malformed or non-timer boundaries using an existing compiled observer')
    parser.add_argument('--build', type=Path, required=True)
    execute(parser.parse_args().build.resolve())

