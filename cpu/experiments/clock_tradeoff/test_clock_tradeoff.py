import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = Path(__file__).resolve().parent
PDS = Path('D:/PDS_2022.2-SP6.4') if os.name == 'nt' else Path('/mnt/d/PDS_2022.2-SP6.4')
MODEL = PDS / 'arch/vendor/pango/verilog/simulation/GTP_GPLL.v'
DIVIDER = PDS / 'ip/module_ip/ipm2l_flex_pll/ipm2l_flex_pll_eval/ipm2l_pll/createDivideParam.tcl'


class ClockTradeoffTests(unittest.TestCase):
    def probe(self, frequency, source=None):
        if source is None:
            source = (EXPERIMENT / 'rv32_pll.sv').read_text()
        with tempfile.TemporaryDirectory(prefix='pll-tradeoff-') as temporary:
            work = Path(temporary)
            rtl = work / 'rv32_pll.sv'
            rtl.write_text(source)
            image = work / 'test.vvp'
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'pll_tb', f'-Ppll_tb.CLOCK_HZ={frequency}', '-o', str(image), str(rtl), str(ROOT / 'sim/pll_tb.sv'), str(MODEL)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=60)

    def test_vendor_clock_and_relock(self):
        for frequency in (153000000, 154285714, 155250000, 157500000):
            with self.subTest(frequency=frequency):
                result = self.probe(frequency)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS PLL clock_hz={frequency} ', result.stdout)
                self.assertIn('reset_relock=1', result.stdout)
                self.assertNotIn('Error', result.stdout + result.stderr)
                print(result.stdout.strip())
        for source in (MODEL, DIVIDER):
            print(source.name, hashlib.sha256(source.read_bytes()).hexdigest().upper())

    def test_static_ratios_in_vendor_bounds(self):
        ratios = {153000000: (1, 1, 34, 6), 154285714: (1, 2, 20, 7), 155250000: (2, 1, 69, 6)}
        for frequency, (input_divider, multiplier, feedback, output_divider) in ratios.items():
            pfd = Fraction(27000000, input_divider)
            vco = pfd * multiplier * feedback
            self.assertTrue(10000000 <= pfd <= 450000000)
            self.assertTrue(600000000 <= vco <= 1200000000)
            self.assertLess(abs(vco / output_divider - frequency), 1)
            self.assertTrue(all(1 <= divider <= 128 for divider in (input_divider, multiplier, feedback, output_divider)))
        vendor = DIVIDER.read_text(encoding='utf-8-sig')
        self.assertIn('set min_clkvco 600.0', vendor)
        self.assertIn('set max_clkvco 1200.0', vendor)

    def test_runtime_divider_mutations(self):
        original = (EXPERIMENT / 'rv32_pll.sv').read_text()
        cases = ((153000000, '(CLOCK_HZ==153000000) ? 34', '(CLOCK_HZ==153000000) ? 35'),
                 (154285714, '(CLOCK_HZ==154285714) ? 7', '(CLOCK_HZ==154285714) ? 6'),
                 (155250000, 'INPUT_DIVIDE=(CLOCK_HZ==155250000 || ', 'INPUT_DIVIDE=('))
        for frequency, before, after in cases:
            with self.subTest(frequency=frequency):
                self.assertEqual(original.count(before), 1)
                result = self.probe(frequency, original.replace(before, after))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('PLL frequency mismatch', result.stdout)
                self.assertNotIn('timeout', result.stdout)

    def test_exact_source_delta(self):
        receipt = json.loads((EXPERIMENT / 'source-delta.json').read_text())
        source = (ROOT / 'experiments/full_mul_precompute/fpga/rv32_pll.sv').read_text()
        for before, after in receipt['edits']:
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        self.assertEqual(source, (EXPERIMENT / 'rv32_pll.sv').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
