import unittest
from fractions import Fraction

from frequency_promotion import Measurement
from frequency_target500 import compare_execution_promotion
from resource_margin_promotion import compare_resource_margin_promotion, check_instrumented_metrics, compare_post_ila_resource_promotion, paired_slacks


class ResourceMarginPolicyTests(unittest.TestCase):
    def setUp(self):
        self.baseline = Measurement(6000, 1885980108, 157500000, 9455)
        self.slacks = ('0.026', '0.026')

    def test_unchanged_execution_can_improve_resources(self):
        candidate = Measurement(6000, 1885980108, 157500000, 9454)
        self.assertFalse(compare_execution_promotion(self.baseline, candidate)['allowed'])
        self.assertTrue(compare_resource_margin_promotion(self.baseline, candidate, self.slacks, self.slacks)['allowed'])

    def test_margin_gain_without_resource_or_execution_loss(self):
        self.assertTrue(compare_resource_margin_promotion(self.baseline, self.baseline, self.slacks, ('0.100', '0.050'))['allowed'])
        self.assertFalse(compare_resource_margin_promotion(self.baseline, self.baseline, self.slacks, self.slacks)['allowed'])
        self.assertFalse(compare_resource_margin_promotion(self.baseline, self.baseline, self.slacks, ('0.100', '0.026'))['allowed'])

    def test_no_tradeoff_hides_a_regression(self):
        for candidate, slacks in (
            (Measurement(6000, 1885980109, 157500000, 9400), ('0.100', '0.100')),
            (Measurement(6000, 1885980108, 157200000, 9400), ('0.100', '0.100')),
            (Measurement(6000, 1885980108, 157500000, 9456), ('0.100', '0.100')),
            (Measurement(6000, 1885980108, 157500000, 9400), ('0.025', '0.100')),
            (Measurement(6000, 1885980108, 157500000, 9400), ('0.100', '-0.001')),
        ):
            with self.subTest(candidate=candidate, slacks=slacks):
                self.assertFalse(compare_resource_margin_promotion(self.baseline, candidate, self.slacks, slacks)['allowed'])

    def test_exact_margin_not_display_rounding(self):
        better = Fraction(26, 1000) + Fraction(1, 10**12)
        worse = Fraction(26, 1000) - Fraction(1, 10**12)
        self.assertEqual(format(float(better), '.3f'), format(float(worse), '.3f'))
        self.assertTrue(compare_resource_margin_promotion(self.baseline, self.baseline, self.slacks, (better, better))['allowed'])
        self.assertFalse(compare_resource_margin_promotion(self.baseline, self.baseline, self.slacks, (worse, worse))['allowed'])

    def test_higher_qualified_clock_is_not_forbidden(self):
        candidate = Measurement(6000, 1885980108, 160000000, 9455)
        self.assertTrue(compare_resource_margin_promotion(self.baseline, candidate, self.slacks, ('0.030', '0.030'))['allowed'])

    def test_ila_may_consume_slack_but_not_hide_total_luts(self):
        self.assertTrue(check_instrumented_metrics(self.baseline, self.baseline, ('0', '0.001'))['allowed'])
        self.assertFalse(check_instrumented_metrics(self.baseline, self.baseline, ('0.100', '-0.001'))['allowed'])
        larger = Measurement(6000, 1885980108, 157500000, 9456)
        self.assertTrue(check_instrumented_metrics(self.baseline, larger, ('0.100', '0.100'))['allowed'])
        slower = Measurement(6000, 1885980109, 157500000, 9400)
        self.assertFalse(check_instrumented_metrics(self.baseline, slower, ('0.100', '0.100'))['allowed'])

    def test_new_ila_resource_floor_is_strict_not_old_0_052(self):
        for luts in (9607, 9942, 10021):
            candidate = Measurement(6000, 1885980108, 157500000, luts)
            self.assertTrue(check_instrumented_metrics(self.baseline, candidate, ('0', '0'))['allowed'])
        candidate = Measurement(6000, 1885980108, 157500000, 10022)
        self.assertFalse(check_instrumented_metrics(self.baseline, candidate, ('0', '0'))['allowed'])
        equal = Measurement(6000, 1875000000, 157500000, 10080)
        self.assertEqual(equal.resource_efficiency, Fraction(1, 20))
        self.assertFalse(check_instrumented_metrics(self.baseline, equal, ('0', '0'))['allowed'])
        above = Measurement(6000, 1875000000, 157500000, 10079)
        self.assertTrue(check_instrumented_metrics(self.baseline, above, ('0', '0'))['allowed'])
        slower_clock = Measurement(6000, 1875000000, 157499999, 10000)
        self.assertFalse(check_instrumented_metrics(self.baseline, slower_clock, ('0', '0'))['allowed'])

    def test_after_hardware_resource_growth_uses_accepted_ila_baseline(self):
        instrumented = Measurement(6000, 1885980108, 157500000, 9942)
        better = Measurement(6000, 1885980108, 157500000, 9941)
        self.assertTrue(compare_post_ila_resource_promotion(instrumented, better, ('0', '0'))['allowed'])
        self.assertFalse(compare_post_ila_resource_promotion(instrumented, instrumented, ('0.1', '0.1'))['allowed'])
        for candidate in (Measurement(6000, 1885980109, 157500000, 9900), Measurement(6000, 1885980108, 157499999, 9900)):
            self.assertFalse(compare_post_ila_resource_promotion(instrumented, candidate, ('0.1', '0.1'))['allowed'])
        self.assertFalse(compare_post_ila_resource_promotion(instrumented, better, ('0.1', '-0.001'))['allowed'])

    def test_invalid_or_incomplete_measurements_rejected(self):
        for values in (None, (), ('0.026',), ('0.026', '0.026', '0.026'), (True, 0), (0.026, 0.026), ('nan', '0'), ('inf', '0'), ('1/0', '0')):
            with self.subTest(values=values), self.assertRaises(ValueError):
                paired_slacks(values)
        for value in (None, {}, 500):
            with self.assertRaises(TypeError):
                compare_resource_margin_promotion(self.baseline, value, self.slacks, self.slacks)
        with self.assertRaises(ValueError):
            compare_resource_margin_promotion(self.baseline, self.baseline, ('-0.001', '0.100'), self.slacks)
        with self.assertRaises(ValueError):
            compare_resource_margin_promotion(Measurement(6000, 1885980108, 151200000, 9000), self.baseline, self.slacks, self.slacks)


if __name__ == '__main__':
    unittest.main(verbosity=2)
