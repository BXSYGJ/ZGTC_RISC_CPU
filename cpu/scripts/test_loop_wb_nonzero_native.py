from hashlib import sha256
from pathlib import Path
import re
import unittest

from loop_wb_nonzero_native import inspect_wb_nonzero_register, pins

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/loop-pending-wb-nonzero-stage/build/pds/20260909-071332-ebc5cdc2/synthesize/pds_soc_top_syn.vm'


class WbQualifierNativeTests(unittest.TestCase):
    def setUp(self):
        self.native = NATIVE.read_text()
        self.result = inspect_wb_nonzero_register(self.native)
        self.flag = next(block for block in re.findall(r'GTP_DFF_CE\b[^;]*;', self.native) if pins(block).get('Q') == 'wb_rd_nonzero')
        self.precompute = next(block for block in re.findall(r'GTP_LUT5\b[^;]*;', self.native) if pins(block).get('Z') == self.result['input'])
        self.enable = next(block for block in re.findall(r'GTP_LUT6CARRY\b[^;]*;', self.native) if pins(block).get('Z') == self.result['enable'])

    def reject_block_change(self, block, before, after):
        self.assertEqual(block.count(before), 1)
        with self.assertRaises(ValueError):
            inspect_wb_nonzero_register(self.native.replace(block, block.replace(before, after)))

    def test_actual_mapped_qualifier(self):
        self.assertEqual((self.result['truth_inputs'], self.result['capture_truth_checks'], self.result['consumers']), (32, 2048, 5))
        self.assertEqual(len(self.result['destination_registers_sha256']), 5)
        print('BOUND WB qualifier native_sha256=' + sha256(NATIVE.read_bytes()).hexdigest().upper())

    def test_flag_capture_controls(self):
        ports = pins(self.flag)
        changes = ((f'.CE ({ports["CE"]})', ".CE (1'b1)"), ('.CLK (clk)', '.CLK (wrong_clock)'),
                   (".INIT(1'b0)", ".INIT(1'b1)"), ('.GRS_EN("TRUE")', '.GRS_EN("FALSE")'))
        for before, after in changes:
            with self.subTest(before=before):
                self.reject_block_change(self.flag, before, after)
                print('PASS WB qualifier capture rejection: ' + before)
        with self.assertRaises(ValueError):
            inspect_wb_nonzero_register(self.native.replace(self.flag, ''))
        print('PASS missing WB qualifier rejection')

    def test_precompute_inputs(self):
        for bit in range(5):
            before = f'.I{bit} (mem_instruction[{bit+7}])'
            after = f'.I{bit} (trace_rd[{bit}])'
            with self.subTest(bit=bit):
                self.reject_block_change(self.precompute, before, after)
                print('PASS WB qualifier stale-source rejection: ' + str(bit))

    def test_truth_consumers_and_enable(self):
        bits = re.search(r"\.INIT\(32'b([01]+)\)", self.precompute)[1]
        self.reject_block_change(self.precompute, bits, bits[:-1] + '1')
        print('PASS WB qualifier zero-truth rejection')
        changed = re.sub(r'(\.I[0-5]\s*\()wb_rd_nonzero\)', r"\g<1>1'b0)", self.native)
        with self.assertRaisesRegex(ValueError, 'no native consumers'):
            inspect_wb_nonzero_register(changed)
        print('PASS WB qualifier dead-consumer rejection')
        self.reject_block_change(self.enable, '.I5_TO_LUT("TRUE")', '.I5_TO_LUT("FALSE")')
        print('PASS WB qualifier unsupported carry-mode rejection')
        bits = re.search(r"\.INIT\(64'b([01]+)\)", self.enable)[1]
        modified = format(int(bits, 2) ^ (1 << 36), '064b')
        self.reject_block_change(self.enable, bits, modified)
        print('PASS WB qualifier enable truth rejection')

    def test_destination_correspondence(self):
        destination = next(block for block in re.findall(r'GTP_DFF_CE\b[^;]*;', self.native) if pins(block).get('Q') == 'trace_rd[0]')
        ports = pins(destination)
        changes = (('.D (mem_instruction[7])', '.D (mem_instruction[8])'),
                   (f'.CE ({ports["CE"]})', ".CE (1'b1)"),
                   ('.C (' + self.result['clear'] + ' )', ".C (1'b0)"))
        for before, after in changes:
            with self.subTest(before=before):
                self.reject_block_change(destination, before, after)
                print('PASS WB destination correspondence rejection: ' + before)

    def test_duplicate_cpu(self):
        with self.assertRaisesRegex(ValueError, 'Ambiguous native CPU module'):
            inspect_wb_nonzero_register(self.native + chr(10) + 'module rv32_core; endmodule' + chr(10))
        print('PASS duplicate native CPU rejection')


if __name__ == '__main__':
    unittest.main(verbosity=2)
