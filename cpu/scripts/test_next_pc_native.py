from pathlib import Path
import unittest

from next_pc_native import SIGNALS,inspect_next_pc_control_boundaries

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/next-pc-enable-reduce-stage/build/pds/20260908-195300-897b4a9c/synthesize/pds_soc_top_syn.vm'


class IrqMergeNativeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(len(inspect_next_pc_control_boundaries(NATIVE.read_text())),5)

    def test_actual_five_boundaries(self):
        self.assertEqual(SIGNALS,('ex_fire_without_irq','ex_fire_with_irq','id_fire_with_irq','fetch_accept_space','next_pc_sequential_write'))

    def test_each_retained_boundary_is_required(self):
        original=NATIVE.read_text()
        for signal in SIGNALS:
            with self.subTest(signal=signal):
                self.assertIn(signal,original)
                with self.assertRaisesRegex(ValueError,'Missing active next PC control boundary'):
                    inspect_next_pc_control_boundaries(original.replace(signal,'removed_retained_boundary'))
                print('PASS retained IRQ boundary rejection: '+signal)

    def test_ambiguous_core_is_rejected(self):
        original=NATIVE.read_text()
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_next_pc_control_boundaries(original+chr(10)+'module rv32_core; endmodule'+chr(10))
        print('PASS ambiguous native CPU rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
