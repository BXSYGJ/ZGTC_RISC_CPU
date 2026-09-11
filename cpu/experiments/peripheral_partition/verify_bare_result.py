import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build/regfile-valid-fanout-stage/scripts'))
from check_coremark import parse_result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate_build_clock(manifest):
    clock_hz = manifest['ClockHz']
    if type(clock_hz) is not int or clock_hz not in (144000000, 146250000, 148500000, 157500000):
        raise ValueError('Unsupported manifest clock')
    clock_flags = [flag for flag in manifest['CompilerFlags'] if flag.startswith('-DCPU_CLOCK_HZ=')]
    if clock_flags != [f'-DCPU_CLOCK_HZ={clock_hz}u']:
        raise ValueError('Compiler clock disagrees with manifest')
    return clock_hz


def verify(build, compiled=False):
    manifest = json.loads((build / 'manifest.json').read_text(encoding='utf-8-sig'))
    clock_hz = validate_build_clock(manifest)
    if manifest['Profile'] != 'NoMmioPeripherals' or manifest['HardwareValidated'] or manifest['FullScoreQualified']:
        raise ValueError('Invalid experimental scope')
    for relative, expected in manifest['SourceHashes'].items():
        source = ROOT / relative if '/' in relative else build / relative
        if digest(source) != expected:
            raise ValueError('Source changed: ' + relative)
    if digest(build / 'coremark.hex') != manifest['FirmwareSha256']:
        raise ValueError('Firmware changed')
    if any((build / name).exists() for name in ('rv32_peripherals.sv', 'rv32_uart.sv')):
        raise ValueError('Unexpected peripheral sources in no-peripheral build')
    if re.search(r'\brv32_(peripherals|uart)\s*#?\s*\(', (build / 'rv32_soc.sv').read_text()):
        raise ValueError('Peripheral instantiated in bare SoC')
    evidence = build / 'compiled' if compiled else build
    if compiled:
        compiled_manifest = json.loads((evidence / 'manifest.json').read_text(encoding='utf-8-sig'))
        if compiled_manifest.get('ClockHz', 157500000) != clock_hz:
            raise ValueError('Simulator clock disagrees with firmware')
        if compiled_manifest['ParentManifestSha256'] != digest(build / 'manifest.json') or compiled_manifest['HardwareValidated']:
            raise ValueError('Compiled source binding changed')
        for relative, expected in compiled_manifest['Artifacts'].items():
            if digest(evidence / relative) != expected:
                raise ValueError('Compiled artifact changed: ' + relative)
    output = (evidence / 'coremark.output').read_text()
    short_run = manifest['Iterations'] == 10
    if manifest['Iterations'] not in (10, 6000):
        raise ValueError('Unsupported iteration count')
    parsed = parse_result(output, allow_short=short_run, expected_clock_hz=clock_hz)
    if parsed['iterations'] != manifest['Iterations'] or parsed['reportable_duration'] is short_run or parsed['validation_run'] is not manifest['ValidationRun']:
        raise ValueError('Unexpected run configuration or duration')
    expected_final = ('c64e' if parsed['validation_run'] else 'fcaf') if short_run else ('18e1' if parsed['validation_run'] else 'a14c')
    if parsed['final_crc'] != expected_final:
        raise ValueError('Final CRC mismatch')
    memory = json.loads((evidence / 'result.json').read_text())
    for key in ('cycles', 'retired', 'clock_hz'):
        if memory[key] != parsed[key]:
            raise ValueError('RAM metadata disagrees with report: ' + key)
    if memory['output_bytes'] != len((evidence / 'coremark.output').read_bytes()):
        raise ValueError('RAM output length mismatch')
    runtime = (evidence / 'execute.log').read_text()
    runtime_label = 'compiled' if compiled else 'CoreMark'
    if not re.fullmatch(r'(?:Bare RTL progress cycles=[0-9]+\s+)*PASS bare ' + runtime_label + r' RAM output cycles=[0-9]+ bytes=[0-9]+\s*', runtime):
        raise ValueError('Unexpected RTL termination')
    return dict(schema=1, profile='NoMmioPeripherals', short_crc_passed=short_run, full_duration_crc_passed=not short_run, hardware_validated=False,
                full_score_qualified=False, physical_metrics_pending=True, result=parsed,
                simulation_kind='compiled_two_state' if compiled else 'icarus_four_state',
                expected_runtime_mmio_requests=0, output_sha256=digest(evidence / 'coremark.output'),
                compiled_sha256=digest(evidence / 'obj/Vrv32_bare_sim' if compiled else build / 'bare.vvp'), runtime_sha256=digest(evidence / 'execute.log'),
                manifest_sha256=digest(build / 'manifest.json'), verifier_sha256=digest(Path(__file__)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('build', type=Path)
    parser.add_argument('--compiled', action='store_true')
    arguments = parser.parse_args()
    result = verify(arguments.build, arguments.compiled)
    evidence = arguments.build / 'compiled' if arguments.compiled else arguments.build
    filename = 'short-qualification.json' if result['short_crc_passed'] else 'full-runtime-qualification.json'
    (evidence / filename).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
