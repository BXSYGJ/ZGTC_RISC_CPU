from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from check_coremark import parse_result


class ClockParserTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / 'build/compiled/20260910-192246-1539589e/coremark.sim.uart').read_text()

    def test_actual_lower_clock_uart(self):
        result = parse_result(self.text, allow_short=True, expected_clock_hz=154285714)
        self.assertEqual(result['clock_hz'], 154285714)
        self.assertTrue(result['crc_valid'])
        self.assertEqual(result['iterations'], 10)
        self.assertFalse(result['reportable_duration'])

    def test_wrong_and_unsupported_clocks_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported frequency'):
            parse_result(self.text, allow_short=True, expected_clock_hz=157500000)
        modified = self.text.replace('clock_hz=154285714', 'clock_hz=154285715')
        with self.assertRaisesRegex(ValueError, 'Unsupported frequency'):
            parse_result(modified, allow_short=True, expected_clock_hz=154285715)

    def test_crc_timer_and_completion_still_checked(self):
        for before, after in (('0xe714', '0xe715'), ('Total ticks      : 19', 'Total ticks      : 20'), ('ZGTC COREMARK FINISHED', 'unfinished')):
            with self.subTest(before=before):
                self.assertEqual(self.text.count(before), 1)
                with self.assertRaises(ValueError):
                    parse_result(self.text.replace(before, after), allow_short=True, expected_clock_hz=154285714)

    def test_short_run_cannot_be_scored(self):
        with self.assertRaisesRegex(ValueError, 'shorter than ten seconds'):
            parse_result(self.text, expected_clock_hz=154285714)


if __name__ == '__main__':
    unittest.main(verbosity=2)

