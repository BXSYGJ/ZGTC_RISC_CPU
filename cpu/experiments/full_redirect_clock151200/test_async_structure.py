import unittest

from audit_async_structure import DEFAULT_NETLIST, audit_text


class AsyncStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DEFAULT_NETLIST.read_text(encoding="utf-8-sig")

    def test_current_synthesis_has_four_two_stage_chains(self):
        result = audit_text(self.text)
        self.assertEqual(len(result["chains"]), 4)
        self.assertFalse(result["electrical_qualified"])
        self.assertFalse(result["metastability_mtbf_proven"])

    def test_each_second_stage_bypass_rejected(self):
        for signal in ("rx_meta", "gpio_meta[0]", "gpio_meta[1]", "reset_pipe[0]"):
            with self.subTest(signal=signal):
                original = ".D (" + signal + ")"
                self.assertEqual(self.text.count(original), 1)
                mutant = self.text.replace(original, ".D (1'b0)")
                with self.assertRaisesRegex(ValueError, "Synchronizer bypass"):
                    audit_text(mutant)

    def test_first_stage_logic_fanout_rejected(self):
        anchor = "    wire rx_meta;"
        mutant = self.text.replace(anchor, anchor + "\n    GTP_LUT1 extra(.I0(rx_meta), .Z(extra_net));")
        with self.assertRaisesRegex(ValueError, "additional named-port fanout"):
            audit_text(mutant)

    def test_first_stage_assign_fanout_rejected(self):
        anchor = "    wire rx_meta;"
        mutant = self.text.replace(anchor, anchor + "\n    assign extra_net = rx_meta;")
        with self.assertRaisesRegex(ValueError, "assign fanout"):
            audit_text(mutant)

    def test_wrong_clock_rejected(self):
        anchor = ".Q (rx_meta),\n            .CLK (clk)"
        self.assertEqual(self.text.count(anchor), 1)
        with self.assertRaisesRegex(ValueError, "kind or clock"):
            audit_text(self.text.replace(anchor, anchor.replace(".CLK (clk)", ".CLK (other_clk)")))

    def test_missing_uart_module_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous module"):
            audit_text(self.text.replace("module rv32_uart", "module omitted_uart"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

