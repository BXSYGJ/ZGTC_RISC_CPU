"""Bind v27 loader observations to exact RTL, firmware, model parameters and UART.

This is a read-only evidence gate. It neither qualifies physical timing nor
reserves/programs a board. Architectural and CoreMark gates remain separate.
"""
import argparse
from pathlib import Path
import re
import zlib
import run_embench as h
from embench_board_evidence import read, parse_frame

SMOKE = frozenset(('instrumentation-dummy', 'crc32', 'xgboost'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contained(directory, category):
    path = Path(directory).resolve()
    require(path.is_relative_to((h.ROOT / category).resolve()), 'Evidence outside project ' + category)
    return path


def safe_name(name):
    require(bool(re.fullmatch(r'[A-Za-z0-9_-]+', name)), 'Unsafe evidence name')
    return name


def local_path(value):
    """Map the recorded Windows/WSL drive path to this host, without shell use."""
    value = str(value).replace('\\', '/')
    if h.ROOT.drive:
        match = re.fullmatch(r'/mnt/([a-zA-Z])/(.*)', value)
        if match:
            value = match[1].upper() + ':/' + match[2]
    else:
        match = re.fullmatch(r'([a-zA-Z]):/(.*)', value)
        if match:
            value = '/mnt/' + match[1].lower() + '/' + match[2]
    return Path(value).resolve()


def command_argument(value):
    value = str(value)
    return str(local_path(value)) if re.match(r'^(?:/mnt/[a-zA-Z]/|[a-zA-Z]:[/\\])', value) else value


def model_command(model, command):
    """Require the actual compile command to name precisely the verified sources."""
    sources = sorted(p for p in (model / 'inputs/rtl').glob('*.sv') if p.name != 'rv32_board_top.sv')
    expected = ['/usr/bin/verilator', '--cc', '--exe', '--build', '--Wall', '-Wno-fatal', '-j', '4',
                '--top-module', 'rv32_observed_soc', '--Mdir', model / 'simulator/objects',
                '-CFLAGS', '-O3 -std=c++14', '-GCLOCK_HZ=3200', '-GBAUD=100', '-GINIT_FILE="firmware.hex"']
    expected += [f'-G{k}={v}' for k, v in h.PARAMS.items()]
    expected += sources + [model / 'inputs/port/rv32_observed_soc.sv', model / 'inputs/port/sim_main.cpp']
    require([command_argument(a) for a in command['argv']] == [command_argument(a) for a in expected],
            'Compile command differs from verified model sources/options')
    require(local_path(command['cwd']) == model / 'simulator', 'Compile working directory differs')


def inventory(directory, hashes):
    for relative, digest in hashes.items():
        p = Path(relative)
        require(not p.is_absolute() and '..' not in p.parts, 'Unsafe source inventory path')
        require(h.sha(directory / p) == digest, 'Source inventory changed: ' + relative)


def compile_parameters(argv):
    values = {}
    for argument in argv:
        if argument.startswith('-G'):
            key, value = argument[2:].split('=', 1)
            require(key not in values, 'Duplicate model parameter')
            values[key] = value
    expected = {key: str(value) for key, value in h.PARAMS.items()}
    expected.update(CLOCK_HZ='3200', BAUD='100', INIT_FILE='"firmware.hex"')
    require(values == expected, 'Model hardware/UART parameters differ')
    require(argv.count('--top-module') == 1 and argv[argv.index('--top-module') + 1] == 'rv32_observed_soc',
            'Model top differs')
    return values


def bind(runs, variants, variant, firmware, workloads=SMOKE):
    variants = contained(variants, 'variants')
    firmware = contained(firmware, 'results')
    safe_name(variant)
    workloads = frozenset(safe_name(n) for n in workloads)
    require(bool(workloads), 'At least one workload required')
    vm = read(variants / 'manifest.json')
    fm = read(firmware / 'manifest.json')
    require(vm.get('protocol') == 'v27' and variant in vm.get('variants', {}), 'Explicit v27 variant required')
    require(fm.get('protocol') == 'v26' and fm.get('status') == 'built', 'Frozen v26 firmware required')
    variant_hash, firmware_hash = h.sha(variants / 'manifest.json'), h.sha(firmware / 'manifest.json')
    inventory(variants / variant, vm['variants'][variant]['hashes'])
    require(h.sha(firmware / 'source-hashes.json') == fm['source_manifest_sha256'], 'Firmware inventory changed')
    inventory(firmware / 'inputs', read(firmware / 'source-hashes.json'))
    applications = {r['workload']: r for r in fm['results']}
    require(workloads <= applications.keys() and 'uart-loader' not in workloads, 'Unknown application workload')
    observations = {name: [] for name in workloads}
    receipts = []
    seen_runs = set()
    for directory in runs:
        run = contained(directory, 'results')
        require(run not in seen_runs, 'Duplicate loader run')
        seen_runs.add(run)
        rm = read(run / 'manifest.json')
        require(rm.get('protocol') == 'v27' and rm.get('status') == 'screening_passed', 'Loader run is not a completed v27 screen')
        require(rm.get('variant_manifest_sha256') == variant_hash, 'Loader RTL manifest differs')
        require(rm.get('firmware_manifest_sha256') == firmware_hash, 'Loader firmware manifest differs')
        require(rm.get('configured_clock_hz') == 153000000, 'Loader configured clock differs')
        require(variant in rm.get('models', {}) and variant in rm.get('modes', []), 'Requested variant model is absent')
        model = run / 'models' / variant
        model_info = rm['models'][variant]
        require(h.sha(model / 'source-hashes.json') == model_info['source_manifest_sha256'], 'Model inventory changed')
        model_sources = read(model / 'source-hashes.json')
        inventory(model / 'inputs', model_sources)
        expected_rtl = {n: d for n, d in vm['variants'][variant]['hashes'].items() if n.startswith('rtl/')}
        require({n: d for n, d in model_sources.items() if n.startswith('rtl/')} == expected_rtl, 'Compiled model RTL differs from variant')
        executable = model / 'simulator/objects/Vrv32_observed_soc'
        require(h.sha(executable) == model_info['executable_sha256'], 'Model executable changed')
        compile_command = read(model / 'simulator/compile.command.json')
        parameters = compile_parameters(compile_command['argv'])
        model_command(model, compile_command)
        compile_log = (model / 'simulator/compile.log').read_text(encoding='utf-8')
        warnings = re.findall(r'^%Warning[^\n]*', compile_log, re.M)
        unexpected = [w for w in warnings if not (w.startswith('%Warning-WIDTH:') and 'rv32_burst_ram.sv:' in w and 'Operator NEQ' in w)]
        require(not unexpected and read(model / 'simulator/warnings.json') == dict(warnings=warnings, unexpected=unexpected), 'Unreviewed model warnings')
        rows = [r for r in rm['results'] if r['variant'] == variant and r['workload'] in workloads]
        require(len({(r['workload'], r['repetition']) for r in rows}) == len(rows), 'Duplicate workload/repetition row')
        for row in rows:
            name = row['workload']
            require(row['status'] == 'passed' and row['returncode'] == 0, 'Loader observation failed')
            require(type(row['repetition']) is int and 1 <= row['repetition'] <= rm['repetitions'], 'Invalid observation repetition')
            work = run / 'runs' / variant / name / str(row['repetition'])
            invocation = read(work / 'simulation.command.json')
            expected_argv = [executable, work / 'uart.log', '2500000000', work / 'application.bin']
            require([command_argument(a) for a in invocation['argv']] == [command_argument(a) for a in expected_argv]
                    and local_path(invocation['cwd']) == work, 'Simulation invocation differs from bound model/workload')
            for filename, key in (('application.bin', 'application_sha256'), ('firmware.hex', 'loader_sha256'),
                                  ('uart.log', 'uart_sha256'), ('simulation.log', 'simulation_log_sha256'),
                                  ('redirect-profile.csv', 'profile_sha256')):
                require(h.sha(work / filename) == row[key], 'Changed loader evidence: ' + filename)
            app = applications[name]
            require(row['application_sha256'] == app['binary_sha256'] == h.sha(firmware / 'workloads' / name / 'firmware.bin'), 'Application identity differs')
            require(row['loader_sha256'] == applications['uart-loader']['firmware_sha256'] == h.sha(firmware / 'workloads/uart-loader/firmware.hex'), 'Loader identity differs')
            binary = (work / 'application.bin').read_bytes()
            require(len(binary) == app['binary_bytes'] and format(zlib.crc32(binary), '08x') == app['ram_crc32'], 'Application size/CRC differs')
            uart = (work / 'uart.log').read_text(encoding='ascii')
            crcs = re.findall(r'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n', uart)
            require(crcs == [(app['ram_crc32'], format(len(binary), '08x'))], 'Loader UART CRC/size differs')
            start = 'EMBENCH START ' + name + ' '
            require(uart.count(start) == 1, 'Missing/duplicate benchmark start')
            parsed, _ = parse_frame(uart[uart.index(start):], name)
            log = (work / 'simulation.log').read_text(encoding='utf-8')
            observer = re.findall(r'^OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)$', log, re.M)
            require(len(observer) == 1, 'Independent counter observation missing/ambiguous')
            require((parsed['cycles'], parsed['retired_instructions']) == (row['cycles'], row['retired_instructions']) == tuple(int(n) for n in observer[0][:2]), 'UART/observer/counter disagreement')
            require(parsed['cpi'] == row['cpi'], 'Recorded CPI differs from measured counters')
            require(int(observer[0][2]) == row['minimum_sp'], 'Stack observation differs')
            observations[name].append(dict(run=str(run), repetition=row['repetition'], cycles=parsed['cycles'],
                retired_instructions=parsed['retired_instructions'], uart_sha256=row['uart_sha256']))
        receipts.append(dict(run=str(run), manifest_sha256=h.sha(run / 'manifest.json'),
            model_source_manifest_sha256=model_info['source_manifest_sha256'], executable_sha256=model_info['executable_sha256'],
            compile_command_sha256=h.sha(model / 'simulator/compile.command.json'), parameters=parameters))
    require(all(observations.values()), 'Required loader workloads missing: ' + ', '.join(n for n, rows in observations.items() if not rows))
    for rows in observations.values():
        require(len({(r['cycles'], r['retired_instructions']) for r in rows}) == 1, 'Repeated workload counters differ')
    return dict(protocol='v27', scope='Verified loader RTL observations; not architectural, physical or hardware qualification',
                variant=variant, variant_manifest_sha256=variant_hash, firmware_manifest_sha256=firmware_hash,
                smoke_workloads_verified=SMOKE <= workloads, runs=receipts, observations=observations)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=Path, nargs='+', required=True)
    p.add_argument('--variants', type=Path, required=True)
    p.add_argument('--variant', required=True)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--workloads', nargs='+', default=sorted(SMOKE))
    args = p.parse_args()
    result = bind(args.runs, args.variants, args.variant, args.firmware, args.workloads)
    print('Verified loader evidence for ' + result['variant'] + ': ' + ', '.join(sorted(result['observations'])))
    print('Architectural, physical, seed-selection and hardware gates remain separate.')


if __name__ == '__main__':
    main()
