from pathlib import Path
import unittest

from timer_byte_native import inspect_timer_byte_boundaries

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/timer-byte-compare-stage/build/pds/20260908-182013-c692581d/synthesize/pds_soc_top_syn.vm'


class TimerByteNativeTests(unittest.TestCase):
    def test_actual_synthesis_boundaries(self):
        self.assertEqual(len(inspect_timer_byte_boundaries(NATIVE.read_text())),16)

    def test_missing_boundary_is_rejected(self):
        original=NATIVE.read_text()
        for byte_index in range(8):
            for relation in ('equal','greater'):
                signal='timer_byte_'+relation+'['+str(byte_index)+']'
                with self.subTest(signal=signal):
                    self.assertIn(signal,original)
                    with self.assertRaisesRegex(ValueError,'Missing active timer byte boundary'):
                        inspect_timer_byte_boundaries(original.replace(signal,'removed_byte_boundary'))
                    print('PASS timer byte native boundary rejection: '+signal)

    def test_driver_high_bits_are_verified(self):
        original=NATIVE.read_text()
        signal='timer_byte_equal[0]'
        begin=original.rindex('GTP_LUT6CARRY',0,original.index('.COUT ('+signal+')'))
        end=original.index(';',begin)+1
        driver=original[begin:end]
        self.assertIn('.I0 (timer_compare[6])',driver)
        wrong=driver.replace('.I0 (timer_compare[6])','.I0 (timer_compare[14])')
        with self.assertRaisesRegex(ValueError,'Timer byte high-bit mapping changed'):
            inspect_timer_byte_boundaries(original[:begin]+wrong+original[end:])
        print('PASS timer byte native bit mapping rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
