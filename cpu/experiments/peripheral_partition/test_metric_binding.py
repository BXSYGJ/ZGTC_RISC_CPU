import copy
import json
import unittest

from qualify_bare_pair import bind_metrics, qualify
from verify_bare_result import ROOT, validate_build_clock


class MetricBindingTests(unittest.TestCase):
    def setUp(self):
        self.simulation = dict(ClockHz=157500000, CompilerFlags=['-DCPU_CLOCK_HZ=157500000u'],
                               FirmwareSha256='ABC', SourceHashes={'rv32_core.sv': 'CORE'}, Iterations=6000,
                               ValidationRun=False)
        self.runtime = dict(clock_hz=157500000, cycles=1885688608, iterations=6000,
                            validation_run=False, crc_valid=True, reportable_duration=True)
        self.physical = dict(ClockHz=157500000, FirmwareSha256='ABC', TimingConstraintsMet=True,
                             SourceSnapshot={'Files': {'rtl/rv32_core.sv': 'CORE'}},
                             ResourceSummary=dict(clock_hz=157500000, constraints_met=True, setup_wns_ns=0.1,
                                                  resources={'post_route_luts': 8000}))

    def test_fixed_cycle_efficiency_is_frequency_independent(self):
        expected_efficiency = 6000 * 1000000 / 1885688608
        scores = []
        for clock in (144000000, 157500000):
            self.simulation['ClockHz'] = clock
            self.simulation['CompilerFlags'] = [f'-DCPU_CLOCK_HZ={clock}u']
            self.runtime['clock_hz'] = clock
            self.physical['ClockHz'] = clock
            self.physical['ResourceSummary']['clock_hz'] = clock
            result = bind_metrics(self.runtime, self.simulation, self.physical)
            self.assertAlmostEqual(result['coremark_per_mhz'], expected_efficiency)
            self.assertAlmostEqual(result['coremark_per_lut'], result['coremark'] / 8000)
            self.assertEqual(result['nonregressing_clock'], clock >= 157500000)
            self.assertFalse(result['hardware_validated'])
            self.assertFalse(result['full_score_qualified'])
            scores.append(result['coremark'])
        self.assertAlmostEqual(scores[0] / scores[1], 144 / 157.5)

    def test_wrong_physical_evidence_is_rejected(self):
        mutations = (
            lambda evidence: evidence.update(ClockHz=144000000),
            lambda evidence: evidence['ResourceSummary'].update(clock_hz=144000000),
            lambda evidence: evidence.update(FirmwareSha256='OTHER'),
            lambda evidence: evidence['SourceSnapshot']['Files'].update({'rtl/rv32_core.sv': 'DIFFERENT'}),
            lambda evidence: evidence['SourceSnapshot']['Files'].update({'rtl/rv32_uart.sv': 'UART'}),
            lambda evidence: evidence.update(TimingConstraintsMet=False),
            lambda evidence: evidence['ResourceSummary'].update(setup_wns_ns=-0.001),
            lambda evidence: evidence['ResourceSummary']['resources'].update(post_route_luts=0),
        )
        for mutation in mutations:
            evidence = copy.deepcopy(self.physical)
            mutation(evidence)
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                bind_metrics(self.runtime, self.simulation, evidence)

    def test_clock_define_must_match_manifest(self):
        for flags in ([], ['-DCPU_CLOCK_HZ=144000000u'], ['-DCPU_CLOCK_HZ=157500000u'] * 2):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                validate_build_clock(dict(self.simulation, CompilerFlags=flags))

    def test_short_or_wrong_seed_result_cannot_be_scored(self):
        for changes in ({'cycles': 10}, {'crc_valid': False}, {'reportable_duration': False},
                        {'validation_run': True}, {'iterations': 10}, {'clock_hz': 144000000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bind_metrics(dict(self.runtime, **changes), self.simulation, self.physical)

    def test_actual_cross_frequency_pair_is_rejected(self):
        build = ROOT / 'build/peripheral-partition/20260909-162552-3646c3e8'
        physical_build = ROOT / 'build/peripheral-partition/pds/20260909-194559-786ec275/result'
        with self.assertRaisesRegex(ValueError, 'clocks must match'):
            qualify(build, physical_build)

    def test_actual_same_clock_pair_has_no_runtime_yet(self):
        build = ROOT / 'build/peripheral-partition/20260909-194530-9ae7baf6'
        physical_build = ROOT / 'build/peripheral-partition/pds/20260909-194559-786ec275/result'
        with self.assertRaises(FileNotFoundError):
            qualify(build, physical_build)


if __name__ == '__main__':
    unittest.main()
