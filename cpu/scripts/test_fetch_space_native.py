from pathlib import Path
import unittest

from fetch_space_native import SIGNALS,inspect_fetch_control_boundaries

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/fetch-space-reduce-stage/build/pds/20260908-193047-0cee7a80/synthesize/pds_soc_top_syn.vm'


class IrqMergeNativeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(len(inspect_fetch_control_boundaries(NATIVE.read_text())),4)

    def test_actual_four_boundaries(self):
        self.assertEqual(SIGNALS,('ex_fire_without_irq','ex_fire_with_irq','id_fire_with_irq','fetch_accept_space'))

    def test_each_retained_boundary_is_required(self):
        original=NATIVE.read_text()
        for signal in SIGNALS:
            with self.subTest(signal=signal):
                self.assertIn(signal,original)
                with self.assertRaisesRegex(ValueError,'Missing active fetch control boundary'):
                    inspect_fetch_control_boundaries(original.replace(signal,'removed_retained_boundary'))
                print('PASS retained IRQ boundary rejection: '+signal)

    def test_ambiguous_core_is_rejected(self):
        original=NATIVE.read_text()
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_fetch_control_boundaries(original+chr(10)+'module rv32_core; endmodule'+chr(10))
        print('PASS ambiguous native CPU rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
