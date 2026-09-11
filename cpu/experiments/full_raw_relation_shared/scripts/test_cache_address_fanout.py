import unittest

from audit_cache_address_fanout import inspect_netlist


def register(label, output, annotated=False):
    attribute = '(* PAP_MAX_FANOUT=64, PAP_PRESERVE="TRUE" *) ' if annotated else ''
    return (attribute + 'GTP_DFF_CE /* ' + label + ' */ #(\n'
            '.GRS_EN("TRUE"), .INIT(1\'b0))\n' + label + ' (\n'
            '.Q (' + output + '), .C (reset), .CE (enable), .CLK (clk), .D (req_address[2]));\n')


def fixture(replicated):
    original = register(r'\request_address[2]', 'address_original', replicated)
    copied = register(r'\request_address_1_copy[2]', 'address_copy', True) if replicated else ''
    other = 'address_copy' if replicated else 'address_original'
    return ('module rv32_cache\n' + original + copied +
            'GTP_LUT4 consumers (.I0(address_original), .I1(address_original), .I2(' + other +
            '), .I3(' + other + '), .Y(result));\nendmodule\n')


class NativeCacheFanoutAudit(unittest.TestCase):
    def test_explicit_lower_fanout_limit(self):
        for limit in (16, 32):
            with self.subTest(limit=limit):
                text = fixture(True).replace('PAP_MAX_FANOUT=64', f'PAP_MAX_FANOUT={limit}')
                report = inspect_netlist(text, limit)['rv32_cache']
                self.assertEqual(report['address_register_cells'], 2)
                self.assertEqual(report['maximum_direct_sink_pin_occurrences'], 2)
                with self.assertRaisesRegex(ValueError, 'native fanout attribute'):
                    inspect_netlist(text, 64)

    def test_direct_pins_and_copy_controls(self):
        baseline = inspect_netlist(fixture(False))["rv32_cache"]
        candidate = inspect_netlist(fixture(True), 64)["rv32_cache"]
        self.assertEqual(baseline["address_register_cells"], 1)
        self.assertEqual(baseline["maximum_direct_sink_pin_occurrences"], 4)
        self.assertEqual(candidate["address_register_cells"], 2)
        self.assertEqual(candidate["extra_same_bit_cells"], 1)
        self.assertEqual(candidate["maximum_direct_sink_pin_occurrences"], 2)

    def test_no_substring_counting(self):
        text = fixture(True).replace('.Y(result)', '.I4(address_original_extra), .Y(result)')
        self.assertEqual(inspect_netlist(text, 64)["rv32_cache"]["maximum_direct_sink_pin_occurrences"], 2)

    def test_bad_copy_connections(self):
        for original, changed in (
            ('.D (req_address[2])', '.D (req_address[3])'),
            ('.CE (enable)', '.CE (wrong_enable)'),
            ('.CLK (clk)', '.CLK (wrong_clock)'),
            ('.C (reset)', '.C (wrong_reset)'),
            (".INIT(1'b0)", ".INIT(1'b1)"),
        ):
            with self.subTest(change=changed):
                text = fixture(True).replace(original, changed, 1)
                with self.assertRaisesRegex(ValueError, 'copies disagree'):
                    inspect_netlist(text, 64)
        with self.assertRaisesRegex(ValueError, 'same output net'):
            inspect_netlist(fixture(True).replace('.Q (address_copy)', '.Q (address_original)'), 64)
        with self.assertRaisesRegex(ValueError, 'duplicate address register ports'):
            inspect_netlist(fixture(True).replace('.Q (address_copy)', '.Q (address_copy), .Q (second_driver)'), 64)

    def test_missing_replication_or_attributes(self):
        with self.assertRaisesRegex(ValueError, 'native fanout attribute'):
            inspect_netlist(fixture(True).replace('PAP_MAX_FANOUT=64', 'PAP_MAX_FANOUT=128', 1), 64)
        with self.assertRaisesRegex(ValueError, 'native fanout attribute'):
            inspect_netlist(fixture(True).replace('PAP_MAX_FANOUT=64, ', '', 1), 64)
        single = fixture(False).replace('GTP_DFF_CE', '(* PAP_MAX_FANOUT=64 *) GTP_DFF_CE')
        with self.assertRaisesRegex(ValueError, 'No replicated'):
            inspect_netlist(single, 64)
        with self.assertRaisesRegex(ValueError, 'No supported native cache modules'):
            inspect_netlist('module unrelated\nendmodule\n', 64)

    def test_inspection_does_not_claim_missing_cell_attributes(self):
        text = fixture(True).replace('PAP_MAX_FANOUT=64, ', '')
        report = inspect_netlist(text)['rv32_cache']
        self.assertEqual(report['address_register_cells'], 2)
        self.assertEqual(report['maximum_direct_sink_pin_occurrences'], 2)
        self.assertTrue(all(cell['native_max_fanout'] is None for cell in report['bits']['2']))
        with self.assertRaisesRegex(ValueError, 'native fanout attribute'):
            inspect_netlist(text, 64)
        wrong_input = text.replace('.D (req_address[2])', '.D (req_address[3])', 1)
        with self.assertRaisesRegex(ValueError, 'copies disagree'):
            inspect_netlist(wrong_input)

    def test_explicit_register_prefix_is_scoped_and_validated(self):
        text = fixture(True).replace('request_address', 'request_index')
        report = inspect_netlist(text, 64, register_prefix='request_index')['rv32_cache']
        self.assertEqual(report['register_prefix'], 'request_index')
        self.assertEqual(report['address_register_cells'], 2)
        with self.assertRaisesRegex(ValueError, 'No address registers'):
            inspect_netlist(text, 64)
        with self.assertRaisesRegex(ValueError, 'Invalid register prefix'):
            inspect_netlist(text, 64, register_prefix='request_.*')

    def test_duplicate_cache_modules_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate native cache module'):
            inspect_netlist(fixture(True) + fixture(True), 64)

    def test_reports_excess_loads_without_calling_them_routed_fanout(self):
        pins = ', '.join(f'.I{index}(address_copy)' for index in range(65))
        text = fixture(True).replace('endmodule', 'EXTRA loads (' + pins + ');\nendmodule')
        report = inspect_netlist(text, 64)["rv32_cache"]
        self.assertEqual(report["maximum_direct_sink_pin_occurrences"], 67)


if __name__ == '__main__':
    unittest.main()
