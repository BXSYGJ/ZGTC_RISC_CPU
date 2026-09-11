import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from load_use_profile import DRIVER_SHA256, extract_cycle_pc, file_hash, firmware_image, load_json, require, trace_records
from run_coremark_compiled import check_simulation_result, verify_artifacts


def verified_build(build):
    manifest = load_json(build / 'manifest.json')
    require(manifest['SimulationPassed'] is True, 'Baseline simulation did not pass')
    verify_artifacts(build, manifest)
    require(file_hash(build / 'coremark.sim.uart') == manifest['UartSha256'], 'UART hash mismatch')
    require(file_hash(build / 'result.json') == manifest['ResultSha256'], 'Result hash mismatch')
    result = load_json(build / 'result.json')
    parsed = check_simulation_result((build / 'coremark.sim.uart').read_text(encoding='ascii'),
                                     manifest['FirmwareBuild'], manifest['HardwareParameters'], True)
    require(parsed == result, 'Stored result differs from parsed UART')
    return manifest, result


def execute(baseline, firmware_manifest, existing_profile=None):
    root = Path(__file__).resolve().parents[1]
    stage = root / 'build' / 'load-use-profile-stage'
    baseline_manifest, baseline_result = verified_build(baseline)
    firmware = load_json(firmware_manifest)
    require(firmware == baseline_manifest['FirmwareBuild'], 'Firmware manifest differs from baseline')
    require(firmware['Iterations'] == 10, 'Retirement profiling is restricted to 10 iterations')
    require(firmware_manifest.name.endswith('.build.json'), 'Invalid firmware manifest suffix')
    stem = firmware_manifest.name[:-11]
    image_path = firmware_manifest.with_name(stem + '.hex')
    elf = firmware_manifest.with_name(stem + '.elf')
    require(file_hash(image_path) == baseline_manifest['FirmwareSha256'] == firmware['HexSha256'], 'Firmware hash mismatch')
    image = firmware_image(image_path)
    expected = baseline_manifest['SourceSnapshot']
    require(len(expected) == 18 and expected['sim/coremark_compiled.cpp'] != DRIVER_SHA256, 'Unexpected baseline source set')
    for relative, digest in expected.items():
        require(file_hash(stage / relative) == (DRIVER_SHA256 if relative == 'sim/coremark_compiled.cpp' else digest),
                f'Profiler must differ only in observer: {relative}')
    invocation = root / 'build' / 'load-use-profile-invocations' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8])
    invocation.mkdir(parents=True)
    prefix = load_json(root / 'build' / 'riscv32-toolchain.json')['ToolPrefix']
    binary = invocation / 'firmware.bin'
    subprocess.run([prefix + 'objcopy', '-O', 'binary', str(elf), str(binary)], check=True)
    elf_image = binary.read_bytes()
    require(len(elf_image) <= len(image) and elf_image.ljust(len(image), b'\0') == image, 'ELF binary differs from flashed image')
    boundaries = {}
    disassembly_hashes = {}
    for function in ('start_time', 'stop_time'):
        disassembly = subprocess.check_output([prefix + 'objdump', '-d', '--disassemble=' + function, str(elf)], text=True)
        output = invocation / (function + '.disassembly.txt')
        output.write_text(disassembly, encoding='utf-8')
        boundaries[function] = extract_cycle_pc(disassembly, image, function)
        disassembly_hashes[function] = file_hash(output)
    require(boundaries['start_time'] != boundaries['stop_time'], 'Timer boundaries must differ')
    configuration = invocation / 'configuration.json'
    configuration.write_text(json.dumps(baseline_manifest['ConfigurationInput'], indent=2) + '\n', encoding='utf-8')
    if existing_profile is None:
        environment = os.environ.copy()
        environment.update(ZGTC_TRACE_START_PC=f"{boundaries['start_time']:x}", ZGTC_TRACE_STOP_PC=f"{boundaries['stop_time']:x}")
        command = [sys.executable, str(stage / 'scripts' / 'run_coremark_compiled.py'), '--configuration', str(configuration),
                   '--firmware-manifest', str(firmware_manifest), '--allow-short', '--max-cycles', '10000000']
        with (invocation / 'runner.log').open('w', encoding='utf-8') as log:
            subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        matches = re.findall(r'^Compiled simulation directory: (.+)$', (invocation / 'runner.log').read_text(encoding='utf-8'), re.M)
        require(len(matches) == 1, 'Missing or ambiguous profiler build')
        build = Path(matches[0]).resolve()
        require(build.parent == (stage / 'build' / 'compiled').resolve(), 'Profiler build outside expected stage')
    else:
        build = existing_profile
    manifest, result = verified_build(build)
    require(manifest['ConfigurationInput'] == baseline_manifest['ConfigurationInput'], 'Profiler configuration changed')
    require(manifest['HardwareParameters'] == baseline_manifest['HardwareParameters'], 'Profiler hardware parameters changed')
    require(manifest['FirmwareBuild'] == firmware and manifest['FirmwareSha256'] == file_hash(image_path), 'Profiler firmware changed')
    require(manifest['SourceSnapshot'] == dict(expected, **{'sim/coremark_compiled.cpp': DRIVER_SHA256}), 'Profiler source snapshot changed')
    require(result == baseline_result and (build / 'coremark.sim.uart').read_bytes() == (baseline / 'coremark.sim.uart').read_bytes(),
            'Observer changed UART, cycles, counters, or CRC')
    trace = build / 'coremark.sim.uart.retire.bin'
    metadata_path = build / 'coremark.sim.uart.retire.json'
    metadata = load_json(metadata_path)
    require(metadata['start_pc'] == boundaries['start_time'] and metadata['stop_pc'] == boundaries['stop_time'], 'Trace timer boundary mismatch')
    require(metadata['cycles'] == result['cycles'], 'Trace span differs from scored cycle interval')
    count = sum(1 for _ in trace_records(trace, metadata, image))
    require(count == metadata['records'], 'Trace count mismatch')
    report = dict(schema=1, measurement_kind='retirement_profile_rtl_not_hardware_or_official_score',
        baseline=str(baseline), build=str(build), invocation=str(invocation), firmware_manifest=str(firmware_manifest),
        baseline_manifest_sha256=file_hash(baseline / 'manifest.json'), profile_manifest_sha256=file_hash(build / 'manifest.json'),
        firmware_sha256=file_hash(image_path), elf_sha256=file_hash(elf), disassembly_sha256=disassembly_hashes,
        observer_sha256=DRIVER_SHA256, trace_sha256=file_hash(trace), trace_metadata_sha256=file_hash(metadata_path),
        library_sha256=file_hash(root / 'scripts' / 'load_use_profile.py'), wrapper_sha256=file_hash(Path(__file__)),
        boundaries=boundaries, metadata=metadata, result=result, unchanged_uart=True, passed=True,
        completed_utc=datetime.now(timezone.utc).isoformat())
    (invocation / 'profile-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description='Source-bound, non-intrusive short CoreMark retirement profiling')
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--firmware-manifest', type=Path, required=True)
    parser.add_argument('--existing-profile', type=Path)
    arguments = parser.parse_args()
    try:
        execute(arguments.baseline.resolve(), arguments.firmware_manifest.resolve(),
                arguments.existing_profile.resolve() if arguments.existing_profile else None)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f'FAIL retirement profile: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

