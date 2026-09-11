import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("clock153_result_parser", ROOT / "scripts/check_coremark.py")
parser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parser)


class ClockParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uart = (ROOT / "build/compiled/20260911-091148-eccded19/coremark.sim.uart").read_text(encoding="ascii")

    def test_actual_153mhz_short_uart(self):
        result = parser.parse_result(self.uart, allow_short=True, expected_clock_hz=153000000)
        self.assertEqual(result["clock_hz"], 153000000)
        self.assertEqual(result["cycles"], 3000565)
        self.assertFalse(result["reportable_duration"])

    def test_mismatched_clock_rejected(self):
        with self.assertRaises(ValueError):
            parser.parse_result(self.uart, allow_short=True, expected_clock_hz=151200000)

    def test_unlisted_clock_rejected(self):
        with self.assertRaises(ValueError):
            parser.parse_result(self.uart.replace("153000000", "153000001"), allow_short=True, expected_clock_hz=153000001)

    def test_short_run_not_a_long_score(self):
        with self.assertRaises(ValueError):
            parser.parse_result(self.uart, expected_clock_hz=153000000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
