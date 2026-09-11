import unittest

from frequency_promotion import Measurement
from frequency_target500 import compare_execution_clock_tradeoff, compare_score_resource_tradeoff


class ScoreResourceTradeoffTests(unittest.TestCase):
    def setUp(self):
        self.baseline = Measurement(6000, 1885980108, 157500000, 9374)

    def test_equal_baseline_allowed(self):
        self.assertTrue(compare_score_resource_tradeoff(self.baseline, self.baseline)["allowed"])

    def test_lower_execution_efficiency_is_reported_not_a_hard_floor(self):
        candidate = Measurement(6000, 1900000000, 160000000, 9374)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertTrue(result["allowed"])
        self.assertTrue(result["execution_efficiency_decreases"])
        self.assertNotIn("execution_efficiency_nondecreasing", result["conditions"])
        self.assertFalse(compare_execution_clock_tradeoff(self.baseline, candidate)["allowed"])

    def test_faster_execution_at_lower_clock_allowed(self):
        candidate = Measurement(6000, 1831572143, 154285714, 9406)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertTrue(result["allowed"])
        self.assertTrue(result["execution_efficiency_increases"])
        self.assertTrue(result["clock_reduced"])

    def test_one_cycle_score_loss_rejected_even_with_fewer_luts(self):
        candidate = Measurement(6000, 1885980109, 157500000, 9000)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertFalse(result["allowed"])
        self.assertFalse(result["conditions"]["coremark_nondecreasing"])
        self.assertTrue(result["conditions"]["resource_efficiency_nondecreasing"])

    def test_resource_loss_rejected_even_with_higher_score(self):
        candidate = Measurement(6000, 1820000000, 154000000, 11000)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertFalse(result["allowed"])
        self.assertTrue(result["conditions"]["coremark_nondecreasing"])
        self.assertFalse(result["conditions"]["resource_efficiency_nondecreasing"])

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(TypeError):
            compare_score_resource_tradeoff(self.baseline, {})
        with self.assertRaises(ValueError):
            compare_score_resource_tradeoff(Measurement(1, 100000000, 27000000, 1000), self.baseline)


if __name__ == "__main__":
    unittest.main(verbosity=2)
