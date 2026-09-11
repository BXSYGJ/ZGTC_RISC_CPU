import unittest

from frequency_promotion import Measurement
from frequency_target500 import compare_execution_clock_tradeoff, coremark


class ExecutionClockTradeoffTests(unittest.TestCase):
    def setUp(self):
        self.baseline = Measurement(6000, 1885980108, 157500000, 9374)
        self.equal_score = Measurement(600000, 1885980108 * 97, 152775000, 9374)

    def test_lower_clock_equal_score_better_execution(self):
        self.assertEqual(coremark(self.baseline), coremark(self.equal_score))
        result = compare_execution_clock_tradeoff(self.baseline, self.equal_score)
        self.assertTrue(result['allowed'])
        self.assertTrue(result['clock_reduced'])
        self.assertTrue(result['execution_efficiency_increases'])
        self.assertIn('not_artifact_or_hardware', result['scope'])

    def test_one_hz_below_score_floor_rejected(self):
        candidate = Measurement(600000, 1885980108 * 97, 152774999, 9374)
        result = compare_execution_clock_tradeoff(self.baseline, candidate)
        self.assertFalse(result['allowed'])
        self.assertFalse(result['conditions']['coremark_nondecreasing'])
        self.assertTrue(result['conditions']['execution_efficiency_nondecreasing'])

    def test_lut_regression_at_equal_score_rejected(self):
        candidate = Measurement(600000, 1885980108 * 97, 152775000, 9375)
        result = compare_execution_clock_tradeoff(self.baseline, candidate)
        self.assertFalse(result['allowed'])
        self.assertTrue(result['conditions']['coremark_nondecreasing'])
        self.assertFalse(result['conditions']['resource_efficiency_nondecreasing'])

    def test_execution_regression_despite_higher_clock_rejected(self):
        candidate = Measurement(6000, 1885980109, 160000000, 9300)
        result = compare_execution_clock_tradeoff(self.baseline, candidate)
        self.assertFalse(result['allowed'])
        self.assertTrue(result['conditions']['coremark_nondecreasing'])
        self.assertFalse(result['conditions']['execution_efficiency_nondecreasing'])

    def test_equal_metrics_are_not_claimed_as_improved(self):
        result = compare_execution_clock_tradeoff(self.baseline, self.baseline)
        self.assertTrue(result['allowed'])
        self.assertFalse(result['execution_efficiency_increases'])

    def test_invalid_inputs_rejected(self):
        for invalid in (None, {}, 6000):
            with self.assertRaises(TypeError):
                compare_execution_clock_tradeoff(invalid, self.equal_score)
            with self.assertRaises(TypeError):
                compare_execution_clock_tradeoff(self.baseline, invalid)
        with self.assertRaises(ValueError):
            compare_execution_clock_tradeoff(Measurement(1, 1000000000, 120000000, 9000), self.equal_score)


if __name__ == '__main__':
    unittest.main(verbosity=2)

