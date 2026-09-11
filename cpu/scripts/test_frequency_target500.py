import unittest
from fractions import Fraction

from frequency_promotion import Measurement
from frequency_target500 import coremark, meets_target, compare_resource_promotion, compare_execution_promotion


class CoreMark500PolicyTests(unittest.TestCase):
    def test_historical_and_conditional_clock_cases(self):
        self.assertFalse(meets_target(Measurement(6000, 1885980108, 151200000, 8979)))
        boundary = Measurement(6000, 1885980108, 157165000, 9236)
        self.assertLess(coremark(boundary), 500)
        self.assertFalse(meets_target(boundary))
        conditional = Measurement(6000, 1885980108, 157500000, 9236)
        self.assertTrue(meets_target(conditional))
        self.assertEqual(coremark(conditional), Fraction(78750000000, 157165009))

    def test_exact_score_boundary_and_efficiency_floors(self):
        exact = Measurement(500, 157500000, 157500000, 9600)
        self.assertEqual(coremark(exact), 500)
        self.assertFalse(meets_target(exact))
        good = Measurement(500, 157165000, 157165000, 9600)
        self.assertTrue(meets_target(good))
        self.assertFalse(meets_target(Measurement(500, 157165001, 157165000, 9600)))
        self.assertFalse(meets_target(Measurement(500, 157165000, 157165000, 9616)))
        self.assertFalse(meets_target(Measurement(500, 150000000, 150000000, 9000)))

    def test_post_target_resource_promotion(self):
        baseline = Measurement(6000, 1885980108, 157500000, 9236)
        better = Measurement(6000, 1885980108, 157500000, 9200)
        self.assertTrue(compare_resource_promotion(baseline, better)['allowed'])
        for candidate in (baseline,
                          Measurement(6000, 1885980108, 157200000, 9000),
                          Measurement(6000, 1885980109, 160000000, 9000),
                          Measurement(6000, 1885980108, 157500000, 9300)):
            self.assertFalse(compare_resource_promotion(baseline, candidate)['allowed'])
        with self.assertRaises(ValueError):
            compare_resource_promotion(Measurement(6000, 1885980108, 151200000, 8979), better)

    def test_post_target_execution_promotion(self):
        baseline = Measurement(6000, 1885980108, 157500000, 9236)
        better = Measurement(6000, 1885980107, 157500000, 9236)
        self.assertTrue(compare_execution_promotion(baseline, better)['allowed'])
        for candidate in (baseline,
                          Measurement(6000, 1885980108, 157500000, 9200),
                          Measurement(6000, 1885980107, 157200000, 9236),
                          Measurement(6000, 1885980107, 157500000, 9237),
                          Measurement(6000, 1885980109, 160000000, 9000)):
            self.assertFalse(compare_execution_promotion(baseline, candidate)['allowed'])
        with self.assertRaises(ValueError):
            compare_execution_promotion(Measurement(6000, 1885980108, 151200000, 8979), better)

    def test_execution_promotion_keeps_exact_resource_floor(self):
        baseline = Measurement(512, 160000000, 160000000, 9000)
        faster = Measurement(512, 150000000, 160000000, 9600)
        self.assertEqual(baseline.resource_efficiency, faster.resource_efficiency)
        self.assertTrue(compare_execution_promotion(baseline, faster)['allowed'])
        lower_resource = Measurement(512, 150000000, 160000000, 9601)
        self.assertTrue(meets_target(lower_resource))
        self.assertFalse(compare_execution_promotion(baseline, lower_resource)['allowed'])

    def test_execution_promotion_does_not_round_small_gain(self):
        baseline = Measurement(6000, 1885980108, 157500000, 9236)
        faster = Measurement(6000, 1885980107, 157500000, 9236)
        self.assertEqual(format(float(baseline.execution_efficiency), '.6f'), format(float(faster.execution_efficiency), '.6f'))
        self.assertTrue(compare_execution_promotion(baseline, faster)['conditions']['execution_efficiency_increases'])

    def test_unvalidated_input_rejected(self):
        for value in (None, {}, 500, '500'):
            with self.assertRaises(TypeError):
                meets_target(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
