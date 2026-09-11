import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from frequency_promotion import Measurement
from frequency_target500 import coremark, meets_target


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact_ratio(value):
    return dict(numerator=value.numerator, denominator=value.denominator)


def baseline_record(report, artifacts):
    require(report.get('measurement_kind') == 'local_PDS_and_RTL_not_hardware', 'Expected local qualification scope')
    require(report.get('local_full_pair_complete') is True, 'Full pair is incomplete')
    require(report.get('updated_target_met') is True, 'Audited target is not met')
    require(set(report['long']) == set(report['pds']) == {'False', 'True'}, 'Expected exactly two paired seeds')
    measurements = {}
    for key in ('False', 'True'):
        physical = report['pds'][key]
        result = report['long'][key]['result']
        require(physical['accepted_manifest'] is True and physical['summary']['constraints_met'] is True, 'Unqualified physical implementation')
        require(result['validation_run'] is (key == 'True'), 'Wrong validation seed')
        require(result['crc_valid'] is True, 'Invalid CRC')
        require(result['measurement_kind'] == 'rtl_simulation_not_hardware', 'Wrong measurement scope')
        measurement = Measurement(result['iterations'], result['cycles'], result['clock_hz'], physical['summary']['resources']['post_route_luts'])
        require(measurement.clock_hz == physical['summary']['clock_hz'], 'Clock does not match physical implementation')
        require(result['modeled_duration_at_least_10s'] is True and measurement.cycles >= 10 * measurement.clock_hz, 'Run shorter than ten seconds')
        measurements[key] = measurement
    performance = measurements['False']
    require(meets_target(performance), 'Exact measured target is not met')
    require(artifacts and all(isinstance(name, str) and isinstance(digest, str) and len(digest) == 64 and set(digest) <= set('0123456789ABCDEF') for name, digest in artifacts.items()), 'Invalid artifact hash inventory')
    return dict(schema=1, scope='local_PDS_and_RTL_not_hardware', hardware_tested=False,
                measurement=asdict(performance),
                exact_metrics=dict(coremark=exact_ratio(coremark(performance)), coremark_per_mhz=exact_ratio(performance.execution_efficiency), coremark_per_lut=exact_ratio(performance.resource_efficiency)),
                physical_builds={key: value['build'] for key, value in report['pds'].items()},
                compiled_builds={key: value['build'] for key, value in report['long'].items()},
                post_target_rule='strict_execution_increase_clock_and_exact_resource_nondecrease',
                qualification=report, artifacts=dict(sorted(artifacts.items())))


def artifact_hash(root, relative):
    root = Path(root).resolve(strict=True)
    path = root / relative
    require(not path.is_symlink(), 'Symbolic-link artifact is not allowed')
    resolved = path.resolve(strict=True)
    require(resolved.is_relative_to(root) and resolved.is_file(), 'Artifact outside project or not a file')
    return hashlib.sha256(resolved.read_bytes()).hexdigest().upper()


def write_exclusive(path, record):
    serialized = json.dumps(record, indent=2, ensure_ascii=False) + chr(10)
    with Path(path).open('x', encoding='utf-8', newline=chr(10)) as handle:
        handle.write(serialized)
