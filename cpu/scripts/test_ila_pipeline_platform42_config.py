import unittest
from pathlib import Path
from ila_pipeline_platform42_config import CORE_PROPERTIES, DATA_NAMES, validate_config

ROOT = Path(__file__).resolve().parents[1]


class Platform42ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / 'scripts/cpu_ila_regfilefanout157500_platform42.fic.in').read_text(encoding='utf-8-sig')
        folder = ROOT / 'build/ila-probe/regfilefanout157500-platform42-named-v2'
        cls.actual = (folder / 'split.fic').read_text(encoding='utf-8-sig')
        cls.output = (folder / 'stdout.txt').read_text(encoding='utf-8-sig')
        validate_config(cls.actual, cls.output)

    def test_actual_mapping_and_line_endings(self):
        result = validate_config(self.actual, self.output)
        self.assertEqual(result, validate_config(self.template))
        self.assertEqual(result['data_channels'], 42)
        self.assertEqual(result['trigger_channels'], 42)
        self.assertFalse(result['platform_capture_verified'])
        self.assertEqual(result, validate_config(self.actual.replace('\n', '\r\n'), self.output.replace('\n', '\r\n')))

    def test_every_shared_channel(self):
        for index, name in enumerate(DATA_NAMES):
            line = f'Project.unit<0>.triggerChannel<0><{index}>={name}'
            self.assertEqual(self.template.count(line + '\n'), 1)
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, 'map mismatch'):
                    validate_config(self.template.replace(line, line + '_wrong'))
        print('PASS all 42 actual shared data/trigger channels individually protected')

    def test_all_properties(self):
        for name, value in CORE_PROPERTIES.items():
            with self.subTest(name=name):
                line = f'Project.unit<0>.{name}={value}'
                with self.assertRaisesRegex(ValueError, 'property mismatch'):
                    validate_config(self.template.replace(line + '\n', line + '_wrong\n'))
        print(f'PASS {len(CORE_PROPERTIES)} exact hardware properties protected')

    def test_wrong_width_or_separate_maps(self):
        for line in ('Project.unit<0>.dataChannel<0>=cpu_clk', 'Project.unit<0>.dataPortWidth=42',
                     'Project.unit<0>.triggerChannel<0><42>=cpu_clk', 'Project.unit<1>.triggerChannel<0><0>=cpu_clk',
                     'Project.unit<0>.clockChannel=cpu_clk', 'Project.unit.dimension=2'):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    validate_config(self.template + line + '\n')
        old = (ROOT / 'scripts/cpu_ila_regfilefanout157500_minimal.fic.in').read_text(encoding='utf-8-sig')
        with self.assertRaises(ValueError):
            validate_config(old)
        print('PASS six extra/duplicate/split-map mutations and old 42/33 profile rejected')

    def test_actual_inserter_output(self):
        for old, new in (('Trigger Channel 41:', 'Trigger Channel 42:'), ('Clock Port channel:', 'wrong clock:'),
                         ('Data Same As Trigger:', 'wrong shared mode:'), ('Data Max Depth:', 'wrong depth:')):
            self.assertIn(old, self.output)
            with self.subTest(old=old):
                with self.assertRaises(ValueError):
                    validate_config(self.actual, self.output.replace(old, new))
        for suffix in ('\nE: synthetic corruption\n', '\nData Channel 0: cpu_clk\n', self.output):
            with self.assertRaises(ValueError):
                validate_config(self.actual, self.output + suffix)
        print('PASS seven corrupted actual query outputs rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)

