import unittest

from audit_joint import Measurement, compare_score_resource_tradeoff, coremark


class ExactBaselineFloorTests(unittest.TestCase):
    def setUp(self):
        self.baseline = Measurement(6000, 1885980108, 157500000, 9374)
        self.equal_tradeoff = Measurement(600000, 1885980108 * 96, 151200000, 9374)

    def test_exact_score_and_resource_equality_allows_clock_tradeoff(self):
        self.assertEqual(coremark(self.equal_tradeoff), coremark(self.baseline))
        self.assertEqual(self.equal_tradeoff.resource_efficiency, self.baseline.resource_efficiency)
        result = compare_score_resource_tradeoff(self.baseline, self.equal_tradeoff)
        self.assertTrue(result["allowed"])
        self.assertTrue(result["clock_reduced"])
        self.assertTrue(result["execution_efficiency_increases"])
        self.assertEqual(result["scope"], "exact_metric_policy_only_not_artifact_or_hardware_qualification")

    def test_one_extra_cycle_below_floor_is_rejected(self):
        candidate = Measurement(600000, 1885980108 * 96 + 1, 151200000, 9374)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertFalse(result["allowed"])
        self.assertFalse(result["conditions"]["coremark_nondecreasing"])

    def test_one_extra_lut_with_equal_score_is_rejected(self):
        candidate = Measurement(600000, 1885980108 * 96, 151200000, 9375)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertTrue(result["conditions"]["coremark_nondecreasing"])
        self.assertFalse(result["conditions"]["resource_efficiency_nondecreasing"])
        self.assertFalse(result["allowed"])

    def test_lower_score_cannot_be_hidden_by_lower_lut_count(self):
        candidate = Measurement(600000, 1885980108 * 96 + 1, 151200000, 9000)
        result = compare_score_resource_tradeoff(self.baseline, candidate)
        self.assertTrue(result["conditions"]["resource_efficiency_nondecreasing"])
        self.assertFalse(result["conditions"]["coremark_nondecreasing"])
        self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
