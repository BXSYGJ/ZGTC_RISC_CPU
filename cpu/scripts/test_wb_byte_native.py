from pathlib import Path
from hashlib import sha256
import re
import subprocess
import tempfile
import unittest

from wb_byte_native import inspect_wb_byte_retime, native_wb_byte_design

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/wb-byte-retime-stage/build/pds/20260909-041604-e83d4473/synthesize/pds_soc_top_syn.vm'


class WbByteNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.report, cls.cells = inspect_wb_byte_retime(cls.native)
        cls.blocks = re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;', cls.native)

    def test_actual_capture(self):
        self.assertEqual(len(self.report['capture_registers']), 16)
        self.assertGreater(len(self.cells), 0)
        print('PASS WB byte native captures=16 cells=' + str(len(self.cells)))
        print('BOUND WB byte native_sha256=' + sha256(NATIVE.read_bytes()).hexdigest().upper())

    def test_capture_mutants(self):
        for capture in self.report['capture_registers']:
            signal = capture['output']
            matches = [block for block in self.blocks if re.search(r'\.Q\s*\(' + re.escape(signal) + r'\s*\)', block)]
            self.assertEqual(len(matches), 1)
            block = matches[0]
            for field, before, after in (('clock', '.CLK (clk)', ".CLK (1'b0)"), ('reset', chr(92) + 'board/soc/N62_0', 'foreign_reset'), ('data', '.D (' + capture['data'] + ')', '.D (foreign_data)'), ('output', signal, 'foreign_output')):
                self.assertEqual(block.count(before), 1)
                changed = self.native.replace(block, block.replace(before, after))
                with self.subTest(signal=signal, field=field), self.assertRaises(ValueError):
                    inspect_wb_byte_retime(changed)
                print('PASS WB byte native rejection: ' + signal + ':' + field)

    def run_vendor(self, native):
        design = native_wb_byte_design(native)
        vendor = Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
        kinds = sorted(set(re.findall(r'\b(GTP_[A-Z0-9_]+)\b', design)))
        models = [vendor / (name + '.v') for name in kinds] + [vendor / name for name in ('GTP_LUT5.v', 'GTP_MUX2LUT6.v', 'INT_LUTMUX2_UDP.v', 'INT_LUTMUX4_UDP.v') if name[:-2] not in kinds]
        with tempfile.TemporaryDirectory(prefix='wb-byte-native-') as temporary:
            directory = Path(temporary)
            source = directory / 'native.sv'
            source.write_text(design)
            image = directory / 'test.vvp'
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'wb_byte_native_tb', '-o', str(image), str(source), str(ROOT / 'sim/wb_byte_native_tb.sv'), *map(str, models)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=180)

    def test_vendor_byte_comparison_cones(self):
        result = self.run_vendor(self.native)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS wb_byte_native checks=524288', result.stdout)
        print(result.stdout.strip())

    def test_vendor_detects_wrong_operand(self):
        block = next(cell for cell in self.cells if 'compare_next_a[0]' in cell)
        changed = self.native.replace(block, block.replace('compare_next_a[0]', 'compare_next_a[1]'))
        result = self.run_vendor(changed)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('FAIL wb_byte_native', result.stdout)
        print('PASS WB byte vendor rejection: wrong_operand_bit')


if __name__ == '__main__':
    unittest.main(verbosity=2)
