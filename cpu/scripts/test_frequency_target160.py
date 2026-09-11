from fractions import Fraction
import unittest

from frequency_promotion import Measurement
from frequency_target160 import compare_measurements,meets_target


class UpdatedClockTargetTests(unittest.TestCase):
    def test_current_frequency_boundary(self):
        for frequency in (150000000,151200000,151875000,159999999):
            with self.subTest(frequency=frequency):
                self.assertFalse(meets_target(Measurement(6000,1885980108,frequency,8979)))
        self.assertTrue(meets_target(Measurement(6000,1885980108,160000000,8979)))
        self.assertTrue(meets_target(Measurement(6000,1885980108,162000000,8979)))

    def test_both_efficiency_floors_still_apply(self):
        self.assertFalse(meets_target(Measurement(6000,1918110244,162000000,8979)))
        self.assertFalse(meets_target(Measurement(6000,1885980108,162000000,10000)))

    def test_old_accepted_baseline_is_not_new_target(self):
        with self.assertRaisesRegex(ValueError,'updated 160 MHz target'):
            compare_measurements(Measurement(6000,1885980108,151200000,8979),Measurement(6000,1885980108,162000000,8979))

    def test_post_target_both_efficiencies_cannot_decline(self):
        baseline = Measurement(6000,1885980108,162000000,8979)
        self.assertTrue(compare_measurements(baseline,Measurement(6000,1885980108,163000000,8979))['allowed'])
        self.assertFalse(compare_measurements(baseline,Measurement(6000,1885980109,163000000,8979))['allowed'])
        limit=baseline.luts*163000000//baseline.clock_hz
        self.assertFalse(compare_measurements(baseline,Measurement(6000,1885980108,163000000,limit+1))['allowed'])
        self.assertFalse(compare_measurements(baseline,baseline)['allowed'])

    def test_independent_exact_cases(self):
        count=0
        for frequency in (151875000,159999999,160000000,162000000):
            for cycles in (1885980108,1886792452,1918110244):
                for luts in (8979,9600,10000):
                    result=Measurement(6000,cycles,frequency,luts)
                    expected=frequency>=160000000 and Fraction(6000000000,cycles)>=Fraction(318,100) and Fraction(6000*frequency,cycles*luts)>=Fraction(52,1000)
                    self.assertEqual(meets_target(result),expected)
                    count+=1
        self.assertEqual(count,36)

    def test_wrong_type_rejected(self):
        with self.assertRaises(TypeError):
            meets_target(dict(clock_hz=162000000))


if __name__ == '__main__':
    unittest.main(verbosity=2)
