from pathlib import Path
import unittest

from irq_control_native import SIGNALS,inspect_irq_control_boundaries

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/irq-late-control-stage/build/pds/20260908-184439-1a09f6a4/synthesize/pds_soc_top_syn.vm'


class IrqControlNativeTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(len(inspect_irq_control_boundaries(NATIVE.read_text())),5)

    def test_actual_five_boundaries(self):
        self.assertEqual(len(inspect_irq_control_boundaries(NATIVE.read_text())),5)

    def test_each_missing_boundary_rejected(self):
        original=NATIVE.read_text()
        for signal in SIGNALS:
            with self.subTest(signal=signal):
                self.assertIn(signal,original)
                with self.assertRaisesRegex(ValueError,'Missing active IRQ control boundary'):
                    inspect_irq_control_boundaries(original.replace(signal,'removed_irq_boundary'))
                print('PASS IRQ native boundary rejection: '+signal)

    def test_alias_driver_must_exist(self):
        original=NATIVE.read_text()
        self.assertIn('assign ex_redirect_without_irq = N126;',original)
        with self.assertRaisesRegex(ValueError,'Missing active IRQ control boundary'):
            inspect_irq_control_boundaries(original.replace('assign ex_redirect_without_irq = N126;','assign ex_redirect_without_irq = absent_driver;'))
        print('PASS IRQ native missing alias driver rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
