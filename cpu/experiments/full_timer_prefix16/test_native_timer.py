import unittest

import audit_native_timer as native


class NativeTimerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.netlist = (native.audit.SOURCE / "synthesize/pds_soc_top_syn.vm").read_text(encoding="utf-8-sig")

    def test_exact_native_chain(self):
        lengths = native.carry_lengths(self.netlist)
        self.assertEqual(len(lengths), 63)
        self.assertEqual(max(lengths.values()), 17)
        self.assertEqual([lengths[bit] for bit in (15, 16, 31, 32, 47, 48, 63)], [15, 1, 16, 1, 16, 2, 17])

    def test_missing_output_rejected(self):
        self.assertEqual(self.netlist.count(".Z (timer_incremented[49])"), 1)
        with self.assertRaisesRegex(ValueError, "Incomplete timer carry outputs"):
            native.carry_lengths(self.netlist.replace(".Z (timer_incremented[49])", ".Z (other_net)"))

    def test_duplicate_output_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate timer output driver"):
            native.carry_lengths(self.netlist.replace(".Z (timer_incremented[49])", ".Z (timer_incremented[48])"))

    def test_duplicate_module_rejected(self):
        with self.assertRaisesRegex(ValueError, "Peripheral module missing or ambiguous"):
            native.carry_lengths(self.netlist + "\nmodule rv32_peripherals; endmodule\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
