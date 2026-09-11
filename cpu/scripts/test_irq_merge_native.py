from pathlib import Path
import unittest

from irq_merge_native import SIGNALS,inspect_irq_control_boundaries

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/irq-control-merge-stage/build/pds/20260908-190504-75c3cc11/synthesize/pds_soc_top_syn.vm'


class IrqMergeNativeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(len(inspect_irq_control_boundaries(NATIVE.read_text())),3)

    def test_actual_three_boundaries(self):
        self.assertEqual(SIGNALS,('ex_fire_without_irq','ex_fire_with_irq','id_fire_with_irq'))

    def test_each_retained_boundary_is_required(self):
        original=NATIVE.read_text()
        for signal in SIGNALS:
            with self.subTest(signal=signal):
                self.assertIn(signal,original)
                with self.assertRaisesRegex(ValueError,'Missing active IRQ control boundary'):
                    inspect_irq_control_boundaries(original.replace(signal,'removed_retained_boundary'))
                print('PASS retained IRQ boundary rejection: '+signal)

    def test_ambiguous_core_is_rejected(self):
        original=NATIVE.read_text()
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_irq_control_boundaries(original+chr(10)+'module rv32_core; endmodule'+chr(10))
        print('PASS ambiguous native CPU rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
