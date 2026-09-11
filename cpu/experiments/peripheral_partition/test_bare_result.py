import json
import unittest
from pathlib import Path
from unittest.mock import patch
from verify_bare_result import ROOT, verify

BUILD = ROOT / 'build/peripheral-partition/20260909-161048-c0e39ccb'


class BareResultTests(unittest.TestCase):
    def test_real_alternate_clock_short_run_remains_unscored(self):
        build = ROOT / 'build/peripheral-partition/20260909-202927-182996d5'
        result = verify(build, compiled=True)
        self.assertEqual(result['result']['clock_hz'], 144000000)
        self.assertEqual(result['result']['cycles'], 3147992)
        self.assertTrue(result['short_crc_passed'])
        self.assertFalse(result['full_score_qualified'])
        self.assertFalse(result['hardware_validated'])

    def test_actual_compiled_result(self):
        result = verify(BUILD, compiled=True)
        self.assertTrue(result['short_crc_passed'])
        self.assertFalse(result['full_score_qualified'])
        self.assertFalse(result['hardware_validated'])
        self.assertEqual(result['result']['cycles'], 3147992)

    def test_wrong_report_or_metadata_rejected(self):
        read_text = Path.read_text
        mutations = [
            ('coremark.output', lambda text: text.replace('0xfcaf', '0xfc00')),
            ('coremark.output', lambda text: text.replace('0xe714', '0xe700')),
            ('coremark.output', lambda text: text.replace('validation=0', 'validation=1')),
            ('coremark.output', lambda text: text.replace('157500000', '120000000')),
            ('coremark.output', lambda text: text.replace('ZGTC COREMARK FINISHED', 'ZGTC TRAP')),
            ('result.json', lambda text: json.dumps(dict(json.loads(text), cycles=1))),
            ('result.json', lambda text: json.dumps(dict(json.loads(text), retired=1))),
            ('result.json', lambda text: json.dumps(dict(json.loads(text), output_bytes=1))),
            ('execute.log', lambda text: 'PASS unrelated test'),
        ]
        for filename, mutation in mutations:
            def modified(source, *arguments, **keywords):
                text = read_text(source, *arguments, **keywords)
                return mutation(text) if source == BUILD / 'compiled' / filename else text
            with self.subTest(filename=filename), patch.object(Path, 'read_text', modified), self.assertRaises(ValueError):
                verify(BUILD, compiled=True)


if __name__ == '__main__':
    unittest.main()
