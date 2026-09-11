import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class IsolatedDataSelect(unittest.TestCase):
    def test_all_binary_controls_and_payload_bits(self):
        with tempfile.TemporaryDirectory(prefix='cache-data-select-isolated-') as temporary:
            image = Path(temporary) / 'selector.vvp'
            compile_result = subprocess.run(['iverilog', '-g2012', '-s', 'cache_data_select_tb', '-o', str(image),
                                             str(ROOT / 'experiments/cache_data_select/rv32_cache.sv'),
                                             str(ROOT / 'sim/cache_data_select_tb.sv')], capture_output=True, text=True, timeout=60)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            result = subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS isolated data selector cases=832 control_combinations=8 walking_bits=96 unknown_patterns=4', result.stdout)
            print(result.stdout.strip())


if __name__ == '__main__':
    unittest.main(verbosity=2)
