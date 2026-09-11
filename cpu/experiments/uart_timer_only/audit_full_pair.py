import argparse
import json
from pathlib import Path

from audit_short_pair import audit, check_simulation_result, file_hash, verify_artifacts
from run_coremark_compiled import hardware_parameters
from pds_report import parse_reports


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def audit_full(stage, console_delay_cycles=2700000):
    short = audit(stage)
    results = []
    baseline_cycles = {False: 1885980108, True: 1888935654}
    minimum_execution = 500000000 / 157165009
    for validation in (False, True):
        simulations = []
        for directory in (stage / 'build/compiled').iterdir():
            manifest = read_json(directory / 'manifest.json')
            firmware = manifest['FirmwareBuild']
            if (manifest['SimulationPassed'] and firmware['Iterations'] == 6000
                    and firmware['ValidationRun'] == validation and firmware['ConsoleDelayCycles'] == console_delay_cycles):
                simulations.append((directory, manifest))
        if len(simulations) != 1:
            raise ValueError(f'Full runtime not yet uniquely complete: validation={validation}')
        directory, simulation = simulations[0]
        verify_artifacts(directory, simulation)
        measured = check_simulation_result((directory / 'coremark.sim.uart').read_text(),
                                           simulation['FirmwareBuild'], simulation['HardwareParameters'], False)
        if measured['clock_hz'] != 157500000 or not measured['modeled_duration_at_least_10s']:
            raise ValueError('Full runtime does not preserve the required clock/duration')
        physical_matches = []
        for build in (stage / 'build/pds').iterdir():
            if not (build / 'manifest.json').exists():
                continue
            physical = read_json(build / 'manifest.json')
            if physical['FirmwareSha256'] == simulation['FirmwareSha256']:
                physical_matches.append((build, physical))
        if len(physical_matches) != 1:
            raise ValueError(f'No unique timing-qualified physical firmware match: validation={validation}')
        build, physical = physical_matches[0]
        if physical['ClockHz'] != measured['clock_hz'] or hardware_parameters(physical) != simulation['HardwareParameters']:
            raise ValueError('Physical clock/configuration mismatch')
        summary = parse_reports((build / 'report_timing/pds_soc_top.rtr').read_text(encoding='utf-8-sig'),
                                (build / 'run.log').read_text(encoding='utf-8-sig'), physical['ClockHz'])
        if summary != physical['ResourceSummary'] or not summary['constraints_met'] or not physical['TimingConstraintsMet']:
            raise ValueError('Physical timing/resource report mismatch')
        if file_hash(build / 'firmware.hex') != simulation['FirmwareSha256']:
            raise ValueError('Physical firmware differs from actual simulation image')
        if file_hash(build / 'generate_bitstream/pds_soc_top.sbit') != physical['BitstreamSha256']:
            raise ValueError('Physical bitstream changed')
        for relative, expected in physical['SourceSnapshot']['Files'].items():
            if file_hash(build / 'source' / relative) != expected or file_hash(stage / relative) != expected:
                raise ValueError('Physical source differs from staged design: ' + relative)
        for relative, expected in simulation['SourceSnapshot'].items():
            if relative.startswith('rtl/') and physical['SourceSnapshot']['Files'].get(relative) != expected:
                raise ValueError('Physical RTL differs from full runtime: ' + relative)
        luts = summary['resources']['post_route_luts']
        if luts <= 0:
            raise ValueError('No physical LUT evidence')
        efficiency = measured['iterations'] * 1000000 / measured['cycles']
        score = measured['iterations'] * measured['clock_hz'] / measured['cycles']
        resource_efficiency = score / luts
        local_gate = measured['cycles'] <= baseline_cycles[validation] and resource_efficiency > 0.05
        if not validation:
            local_gate = local_gate and efficiency >= minimum_execution and score >= 500
        results.append(dict(validation_run=validation, simulation_build=directory.name, physical_build=build.name,
                            clock_hz=measured['clock_hz'], cycles=measured['cycles'], retired=measured['retired'],
                            coremark=score, coremark_per_mhz=efficiency, coremark_per_lut=resource_efficiency,
                            post_route_luts=luts, setup_wns_ns=summary['setup_wns_ns'],
                            firmware_sha256=simulation['FirmwareSha256'], bitstream_sha256=physical['BitstreamSha256'],
                            simulation_manifest_sha256=file_hash(directory / 'manifest.json'),
                            physical_manifest_sha256=file_hash(build / 'manifest.json'), local_gate_passed=local_gate))
    return dict(schema=1, console_delay_cycles=console_delay_cycles, profile='UART/timer/performance services; no GPIO controller or ILA',
                short_pair_identical=short['short_pair_identical'], full_local_pair_passed=all(result['local_gate_passed'] for result in results),
                measurement_kind='same-artifact RTL/PDS projection, not remote hardware',
                hardware_validated=False, full_goal_complete=False, results=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', type=Path)
    parser.add_argument('--console-delay-cycles', type=int, choices=(0, 2700000), default=2700000)
    arguments = parser.parse_args()
    result = audit_full(arguments.stage, arguments.console_delay_cycles)
    output_name = f'full-local-qualification-p{arguments.console_delay_cycles}.json'
    (arguments.stage / output_name).write_text(json.dumps(result, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps(result, indent=2))
