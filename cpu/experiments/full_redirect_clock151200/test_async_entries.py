import unittest

from audit_async_entries import ROOT, STAGES, audit_text


class AsyncEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "build/ila" / STAGES[0] / "netlist.v").read_text(encoding="utf-8-sig")

    def inject_uart(self, extra):
        anchor = "    wire rx_meta;"
        self.assertEqual(self.text.count(anchor), 1)
        return self.text.replace(anchor, anchor + "\n" + extra)

    def test_all_actual_implementation_inputs(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                result = audit_text((ROOT / "build/ila" / stage / "netlist.v").read_text(encoding="utf-8-sig"))
                self.assertTrue(result["raw_input_paths_passed"])
                self.assertEqual(result["hierarchy_links_checked"], 7)
                self.assertFalse(result["electrical_qualified"])
                self.assertFalse(result["post_route_placement_checked"])

    def test_extra_raw_pin_logic_rejected(self):
        with self.assertRaisesRegex(ValueError, "raw-input consumer"):
            audit_text(self.inject_uart("    GTP_LUT1 leak(.I0(serial_rx), .Z(extra_net));"))

    def test_raw_pin_alias_assignment_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unparsed raw-input"):
            audit_text(self.inject_uart("    wire extra_net;\n    assign extra_net=serial_rx;"))

    def test_initialized_wire_cannot_hide_raw_use(self):
        with self.assertRaisesRegex(ValueError, "Unparsed raw-input"):
            audit_text(self.inject_uart("    wire extra_net=serial_rx;"))

    def test_nested_unknown_expression_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Unparsed raw-input"):
            audit_text(self.inject_uart("    GTP_LUT1 leak(.I0((serial_rx)), .Z(extra_net));"))

    def test_wrong_child_module_rejected(self):
        anchor = "    rv32_uart uart ("
        self.assertEqual(self.text.count(anchor), 1)
        with self.assertRaisesRegex(ValueError, "input-path instance"):
            audit_text(self.text.replace(anchor, "    other_uart uart ("))

    def test_raw_uart_sync_bypass_rejected(self):
        anchor = ".D (rx_meta)"
        self.assertEqual(self.text.count(anchor), 1)
        with self.assertRaisesRegex(ValueError, "Synchronizer bypass"):
            audit_text(self.text.replace(anchor, ".D (serial_rx)"))

    def test_comments_and_lookalike_names_are_not_consumers(self):
        result = audit_text(self.inject_uart("    wire serial_rx_debug;\n    // serial_rx is a raw input\n    /* serial_rx metadata only */"))
        self.assertTrue(result["raw_input_paths_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
