import argparse
import json
import sys
from pathlib import Path

from load_use_profile import DRIVER_SHA256, compare_records, extract_cycle_pc, file_hash, firmware_image, load_json, require, trace_records
from run_load_use_profile import verified_build


def verified_profile(path):
    report = load_json(path)
    root = Path(__file__).resolve().parents[1]
    require(report['passed'] is True and report['unchanged_uart'] is True, 'Unverified profile report')
    require(report['library_sha256'] == file_hash(root / 'scripts' / 'load_use_profile.py'), 'Re-audit profile with current trace library')
    require(report['wrapper_sha256'] == file_hash(root / 'scripts' / 'run_load_use_profile.py'), 'Re-audit profile with current wrapper')
    build = Path(report['build'])
    original = Path(report['baseline'])
    manifest, result = verified_build(build)
    baseline, original_result = verified_build(original)
    require(file_hash(build / 'manifest.json') == report['profile_manifest_sha256'], 'Profile manifest changed')
    require(file_hash(original / 'manifest.json') == report['baseline_manifest_sha256'], 'Original manifest changed')
    require(manifest['SourceSnapshot'] == dict(baseline['SourceSnapshot'], **{'sim/coremark_compiled.cpp': DRIVER_SHA256}), 'Hardware or runner changed')
    require(manifest['HardwareParameters'] == baseline['HardwareParameters'], 'Original hardware parameters changed')
    require(manifest['FirmwareBuild'] == baseline['FirmwareBuild'], 'Original firmware metadata changed')
    require(manifest['FirmwareSha256'] == baseline['FirmwareSha256'] == report['firmware_sha256'], 'Firmware changed')
    require(result == original_result == report['result'], 'Reported timing or CRC changed')
    require((build / 'coremark.sim.uart').read_bytes() == (original / 'coremark.sim.uart').read_bytes(), 'Observer changed UART')
    trace = build / 'coremark.sim.uart.retire.bin'
    metadata_path = build / 'coremark.sim.uart.retire.json'
    require(file_hash(trace) == report['trace_sha256'], 'Trace hash mismatch')
    require(file_hash(metadata_path) == report['trace_metadata_sha256'], 'Trace metadata hash mismatch')
    metadata = load_json(metadata_path)
    require(metadata == report['metadata'] and metadata['cycles'] == result['cycles'], 'Trace interval metadata mismatch')
    image = firmware_image(build / 'firmware.hex')
    firmware_manifest = Path(report['firmware_manifest'])
    require(load_json(firmware_manifest) == manifest['FirmwareBuild'], 'Firmware build manifest changed')
    elf = firmware_manifest.with_name(firmware_manifest.name[:-11] + '.elf')
    require(file_hash(elf) == report['elf_sha256'], 'ELF changed')
    for function, key in (('start_time', 'start_pc'), ('stop_time', 'stop_pc')):
        disassembly = Path(report['invocation']) / (function + '.disassembly.txt')
        require(file_hash(disassembly) == report['disassembly_sha256'][function], 'Timer disassembly changed')
        require(extract_cycle_pc(disassembly.read_text(encoding='utf-8'), image, function) == metadata[key], 'Timer boundary changed')
    return report, manifest, trace_records(trace, metadata, image)


def execute(baseline_path, bubble_path, output):
    baseline, baseline_manifest, baseline_records = verified_profile(baseline_path)
    bubble, bubble_manifest, bubble_records = verified_profile(bubble_path)
    require(baseline_manifest['SourceSnapshot'] == bubble_manifest['SourceSnapshot'], 'Compared sources differ')
    require(baseline_manifest['FirmwareBuild'] == bubble_manifest['FirmwareBuild'], 'Compared firmware differs')
    parameters = baseline_manifest['HardwareParameters']
    require(parameters['LOAD_USE_BUBBLE'] == 0, 'Expected bubble-disabled reference')
    require(bubble_manifest['HardwareParameters'] == dict(parameters, LOAD_USE_BUBBLE=1), 'Unexpected parameter difference')
    analysis = compare_records(baseline_records, bubble_records)
    groups = analysis['groups'].values()
    require(sum(group['baseline_cycles'] for group in groups) == baseline['result']['cycles'], 'Reference gap sum mismatch')
    require(sum(group['candidate_cycles'] for group in groups) == bubble['result']['cycles'], 'Bubble gap sum mismatch')
    delta = bubble['result']['cycles'] - baseline['result']['cycles']
    require(sum(group['delta_cycles'] for group in groups) == delta, 'Gap delta sum mismatch')
    require(sum(group['intervals'] for group in groups) == analysis['intervals'], 'Interval count mismatch')
    analysis.update(schema=1, baseline_report=str(baseline_path), bubble_report=str(bubble_path),
        baseline_report_sha256=file_hash(baseline_path), bubble_report_sha256=file_hash(bubble_path),
        analysis_script_sha256=file_hash(Path(__file__)), library_sha256=file_hash(Path(__file__).with_name('load_use_profile.py')),
        baseline_cycles=baseline['result']['cycles'], bubble_cycles=bubble['result']['cycles'], delta_cycles=delta,
        validation_run=baseline['result']['validation_run'], passed=True)
    output.write_text(json.dumps(analysis, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in analysis.items() if key not in ('transitions', 'groups')}, indent=2))
    print(json.dumps(analysis['groups'], indent=2))
    return analysis


def main():
    parser = argparse.ArgumentParser(description='Compare matched instruction retirement sequences with load-use bubbling toggled')
    parser.add_argument('--baseline-report', type=Path, required=True)
    parser.add_argument('--bubble-report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    try:
        execute(arguments.baseline_report.resolve(), arguments.bubble_report.resolve(), arguments.output.resolve())
    except (ValueError, KeyError, OSError) as error:
        print(f'FAIL trace comparison: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

