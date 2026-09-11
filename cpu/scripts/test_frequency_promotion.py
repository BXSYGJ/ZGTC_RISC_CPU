from dataclasses import FrozenInstanceError
from fractions import Fraction
import unittest

from frequency_promotion import Measurement, compare_measurements


class FrequencyPromotionTests(unittest.TestCase):
    def setUp(self):
        self.baseline = Measurement(318,100000000,150000000,9000)

    def test_equal_efficiencies_with_higher_frequency(self):
        candidate=Measurement(318,100000000,151200000,9072)
        self.assertTrue(compare_measurements(self.baseline,candidate)['allowed'])
        self.assertEqual(self.baseline.resource_efficiency,candidate.resource_efficiency)

    def test_one_cycle_execution_loss_is_rejected(self):
        candidate=Measurement(318,100000001,160000000,8800)
        result=compare_measurements(self.baseline,candidate)
        self.assertFalse(result['allowed'])
        self.assertFalse(result['conditions']['execution_efficiency_nondecreasing'])

    def test_one_lut_resource_loss_is_rejected_even_above_floor(self):
        candidate=Measurement(318,100000000,151200000,9073)
        self.assertTrue(candidate.meets_target)
        self.assertFalse(compare_measurements(self.baseline,candidate)['allowed'])

    def test_equal_or_lower_frequency_is_not_a_promotion(self):
        for frequency in (150000000,149999999):
            result=compare_measurements(self.baseline,Measurement(318,99999999,frequency,8800))
            self.assertFalse(result['allowed'])
            self.assertFalse(result['conditions']['frequency_increases'])

    def test_baseline_cannot_be_an_undervolume_target(self):
        for baseline in (Measurement(318,100000000,146250000,8800),Measurement(318,100000001,151200000,8800),Measurement(318,100000000,151200000,10000)):
            with self.assertRaisesRegex(ValueError,'baseline must already meet'):
                compare_measurements(baseline,self.baseline)

    def test_promotion_chain_compares_previous_accepted_version(self):
        accepted=Measurement(318,99000000,160000000,8900)
        later=Measurement(318,99500000,162000000,8900)
        self.assertTrue(compare_measurements(self.baseline,accepted)['allowed'])
        self.assertTrue(compare_measurements(self.baseline,later)['allowed'])
        self.assertFalse(compare_measurements(accepted,later)['allowed'])

    def test_input_domain_and_immutability(self):
        for index in range(4):
            for invalid in (0,-1,True,1.0):
                values=[318,100000000,150000000,9000]
                values[index]=invalid
                with self.assertRaises(ValueError):
                    Measurement(*values)
        with self.assertRaises(TypeError):
            compare_measurements({},self.baseline)
        with self.assertRaises(FrozenInstanceError):
            self.baseline.cycles=1

    def test_cross_product_reference(self):
        cases=0
        for cycles in (99000000,100000000,100000001):
            for clock in (149999999,150000000,151200000,162000000):
                for luts in (8800,9000,9072,9073,10000):
                    candidate=Measurement(318,cycles,clock,luts)
                    expected=clock>150000000 and Fraction(318000000,cycles)>=Fraction(318,100) and Fraction(318*clock,cycles*luts)>=Fraction(53,1000)
                    self.assertEqual(compare_measurements(self.baseline,candidate)['allowed'],expected)
                    cases+=1
        self.assertEqual(cases,60)
        print('PASS frequency promotion independent rational cases=60')


if __name__ == '__main__':
    unittest.main(verbosity=2)
