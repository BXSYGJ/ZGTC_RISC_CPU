import argparse
import json
from pathlib import Path

from verify_bare_result import digest, validate_build_clock, verify
from pds_report import parse_reports


def bind_metrics(runtime, simulation, physical):
    clock_hz = validate_build_clock(simulation)
    resources = physical['ResourceSummary']
    if runtime['clock_hz'] != clock_hz or physical['ClockHz'] != clock_hz or resources['clock_hz'] != clock_hz:
        raise ValueError('Runtime, firmware and physical clocks must match')
    if simulation['FirmwareSha256'].upper() != physical['FirmwareSha256'].upper():
        raise ValueError('Runtime and physical firmware must match')
    rtl_hashes = {name: value for name, value in simulation['SourceHashes'].items()
                  if name.endswith('.sv') and name != 'coremark_bare_tb.sv'}
    physical_rtl = {Path(name).name: value for name, value in physical['SourceSnapshot']['Files'].items()
                    if name.startswith('rtl/') and name.endswith('.sv')}
    if not rtl_hashes or rtl_hashes != physical_rtl:
        raise ValueError('Runtime and physical RTL must match exactly')
    if not physical['TimingConstraintsMet'] or not resources['constraints_met'] or resources['setup_wns_ns'] < 0:
        raise ValueError('Physical timing constraints failed')
    if not runtime['crc_valid'] or not runtime['reportable_duration'] or runtime['iterations'] != simulation['Iterations']:
        raise ValueError('Full-duration matching CRC result required')
    if runtime['validation_run'] != simulation['ValidationRun']:
        raise ValueError('Runtime seed mode mismatch')
    cycles = runtime['cycles']
    iterations = runtime['iterations']
    luts = resources['resources']['post_route_luts']
    if type(cycles) is not int or cycles <= 0 or type(iterations) is not int or iterations <= 0 or type(luts) is not int or luts <= 0:
        raise ValueError('Positive cycles, iterations and LUT count required')
    seconds = cycles / clock_hz
    if seconds < 10:
        raise ValueError('Runtime shorter than ten seconds')
    efficiency = iterations * 1000000 / cycles
    score = iterations * clock_hz / cycles
    return dict(clock_hz=clock_hz, cycles=cycles, iterations=iterations, seconds=seconds,
                coremark=score, coremark_per_mhz=efficiency, coremark_per_lut=score / luts,
                post_route_luts=luts, setup_wns_ns=resources['setup_wns_ns'],
                nonregressing_clock=clock_hz >= 157500000, resource_threshold_passed=score / luts > 0.05,
                scope='same-artifact RTL/PDS projection only; not board measurement',
                hardware_validated=False, full_score_qualified=False)


def qualify(build, physical_build):
    simulation = json.loads((build / 'manifest.json').read_text(encoding='utf-8-sig'))
    physical = json.loads((physical_build / 'manifest.json').read_text(encoding='utf-8-sig'))
    if validate_build_clock(simulation) != physical['ClockHz']:
        raise ValueError('Runtime, firmware and physical clocks must match')
    runtime = verify(build, compiled=True)
    resources = parse_reports((physical_build / 'report_timing/pds_soc_top.rtr').read_text(encoding='utf-8-sig'),
                              (physical_build / 'run.log').read_text(encoding='utf-8-sig'), physical['ClockHz'])
    if resources != physical['ResourceSummary']:
        raise ValueError('Physical summary differs from raw reports')
    for relative, expected in physical['SourceSnapshot']['Files'].items():
        if digest(physical_build / 'source' / relative) != expected.upper():
            raise ValueError('Physical source changed: ' + relative)
    if digest(physical_build / 'firmware.hex') != physical['FirmwareSha256'].upper():
        raise ValueError('Physical firmware changed')
    if digest(physical_build / 'generate_bitstream/pds_soc_top.sbit') != physical['BitstreamSha256'].upper():
        raise ValueError('Physical bitstream changed')
    result = bind_metrics(runtime['result'], simulation, physical)
    result['runtime_manifest_sha256'] = digest(build / 'manifest.json')
    result['physical_manifest_sha256'] = digest(physical_build / 'manifest.json')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('build', type=Path)
    parser.add_argument('physical_build', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.build, arguments.physical_build), indent=2))
