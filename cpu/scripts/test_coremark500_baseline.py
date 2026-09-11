import copy
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from coremark500_baseline import artifact_hash, baseline_record, write_exclusive


def synthetic_report():
    result = dict(validation_run=False, iterations=6000, cycles=1875000000, clock_hz=157500000,
                  crc_valid=True, modeled_duration_at_least_10s=True, measurement_kind='rtl_simulation_not_hardware')
    physical = dict(build='synthetic-pds-performance', accepted_manifest=True,
                    summary=dict(constraints_met=True, clock_hz=157500000, resources=dict(post_route_luts=9455)))
    report = dict(measurement_kind='local_PDS_and_RTL_not_hardware', local_full_pair_complete=True,
                  updated_target_met=True, pds={'False': physical, 'True': copy.deepcopy(physical)},
                  long={'False': dict(build='synthetic-performance', result=result),
                        'True': dict(build='synthetic-validation', result=copy.deepcopy(result))})
    report['long']['True']['result']['validation_run'] = True
    report['pds']['True']['build'] = 'synthetic-pds-validation'
    return report


class CoreMark500BaselineTests(unittest.TestCase):
    def test_exact_synthetic_metrics_and_scope(self):
        record = baseline_record(synthetic_report(), {'synthetic.txt': 'A' * 64})
        self.assertEqual(record['exact_metrics']['coremark'], dict(numerator=504, denominator=1))
        self.assertEqual(record['exact_metrics']['coremark_per_mhz'], dict(numerator=16, denominator=5))
        resource = Fraction(504, 9455)
        self.assertEqual(record['exact_metrics']['coremark_per_lut'], dict(numerator=resource.numerator, denominator=resource.denominator))
        self.assertIs(record['hardware_tested'], False)
        self.assertEqual(record['scope'], 'local_PDS_and_RTL_not_hardware')

    def test_rejects_incomplete_or_misbound_pair(self):
        mutations = (
            ('scope', lambda report: report.update(measurement_kind='hardware'), 'scope'),
            ('incomplete', lambda report: report.update(local_full_pair_complete=False), 'incomplete'),
            ('boolean', lambda report: report.update(local_full_pair_complete=1), 'incomplete'),
            ('target', lambda report: report.update(updated_target_met=False), 'target'),
            ('missing_seed', lambda report: report['long'].pop('True'), 'two paired'),
            ('timing', lambda report: report['pds']['True']['summary'].update(constraints_met=False), 'physical'),
            ('manifest', lambda report: report['pds']['True'].update(accepted_manifest=False), 'physical'),
            ('seed', lambda report: report['long']['True']['result'].update(validation_run=False), 'seed'),
            ('crc', lambda report: report['long']['True']['result'].update(crc_valid=False), 'CRC'),
            ('measurement', lambda report: report['long']['False']['result'].update(measurement_kind='hardware'), 'scope'),
            ('clock', lambda report: report['long']['False']['result'].update(clock_hz=160000000), 'Clock'),
            ('duration', lambda report: report['long']['False']['result'].update(cycles=100000000), 'ten seconds'),
            ('duration_flag', lambda report: report['long']['False']['result'].update(modeled_duration_at_least_10s=False), 'ten seconds'),
            ('rounded_score', lambda report: report['long']['False']['result'].update(cycles=1890000001), 'Exact'),
            ('area', lambda report: report['pds']['False']['summary']['resources'].update(post_route_luts=10000), 'Exact'),
        )
        for name, mutate, reason in mutations:
            with self.subTest(name=name):
                report = synthetic_report()
                mutate(report)
                with self.assertRaisesRegex(ValueError, reason):
                    baseline_record(report, {'synthetic.txt': 'A' * 64})

    def test_artifact_inventory_and_path_boundary(self):
        for inventory in ({}, {'bad': 'Z' * 64}, {'bad': 'A' * 63}, {'bad': None}):
            with self.subTest(inventory=inventory), self.assertRaisesRegex(ValueError, 'inventory'):
                baseline_record(synthetic_report(), inventory)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            root.mkdir()
            inside = root / 'evidence.txt'
            inside.write_text('synthetic-only', encoding='utf-8')
            self.assertEqual(len(artifact_hash(root, 'evidence.txt')), 64)
            outside = Path(temporary) / 'outside.txt'
            outside.write_text('not-project', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'outside project'):
                artifact_hash(root, '../outside.txt')
            with self.assertRaisesRegex(ValueError, 'not a file'):
                artifact_hash(root, '.')

    def test_exclusive_write_preserves_existing_bytes(self):
        record = baseline_record(synthetic_report(), {'synthetic.txt': 'A' * 64})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'baseline.json'
            write_exclusive(path, record)
            original = path.read_bytes()
            self.assertEqual(json.loads(original), record)
            with self.assertRaises(FileExistsError):
                write_exclusive(path, dict(replaced=True))
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
