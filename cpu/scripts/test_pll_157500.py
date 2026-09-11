import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/clock157500/rv32_pll.sv'
PARENT = ROOT / 'experiments/clock151200/rv32_pll.sv'
MODEL = Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation/GTP_GPLL.v')
BENCH = ROOT / 'sim/pll_tb.sv'


class Pll157500Tests(unittest.TestCase):
    def probe(self, source):
        self.assertTrue(MODEL.is_file(), 'Installed original vendor model required')
        with tempfile.TemporaryDirectory(prefix='pll-157500-') as temporary:
            folder = Path(temporary)
            rtl = folder / 'pll.sv'
            image = folder / 'pll.vvp'
            rtl.write_text(source, encoding='utf-8')
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'pll_tb',
                                       '-Ppll_tb.CLOCK_HZ=157500000', '-o', str(image),
                                       str(rtl), str(BENCH), str(MODEL)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=60)

    def test_exact_canonical_delta(self):
        source = SOURCE.read_text()
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper(), '2C1CD3AF9EC31585DB7EF8870BAE7C9883B1B3ECFA5E457E703639627A55B28D')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), '67677D07E5D35699AFA9C588B7D92DCB3D81DCBEC881CC4CB44D1060D360D0BF')
        restored = source.replace('CLOCK_HZ==157500000 || ', '')
        restored = restored.replace('(CLOCK_HZ==157500000) ? 35 : ', '')
        self.assertEqual(restored, PARENT.read_text())
        self.assertEqual(source.count('CLOCK_HZ==157500000'), 3)

    def test_actual_vendor_clock_and_relock(self):
        result = self.probe(SOURCE.read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS PLL clock_hz=157500000 ', result.stdout)
        self.assertIn('reset_relock=1', result.stdout)
        print(result.stdout.strip())

    def test_wrong_dividers_are_runtime_rejected(self):
        source = SOURCE.read_text()
        mutations = (
            ('feedback', '(CLOCK_HZ==157500000) ? 35 : ', '(CLOCK_HZ==157500000) ? 34 : '),
            ('multiplier', 'MULTIPLIER_DIVIDE=(CLOCK_HZ==157500000 || ', 'MULTIPLIER_DIVIDE=('),
            ('output', '(CLOCK_HZ==157500000 || CLOCK_HZ==144000000', '(CLOCK_HZ==144000000'),
        )
        for name, before, after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before), 1)
                result = self.probe(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PLL frequency mismatch', result.stdout)
                print('PASS actual vendor PLL divider rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
