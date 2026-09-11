import hashlib
from pathlib import Path
import re
import unittest

from predictor_index_native import inspect_predictor_index

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/predictor-index-maxfan-stage/build/pds/20260909-033846-fb07f70e/synthesize/pds_soc_top_syn.vm'


class PredictorIndexNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.result = inspect_predictor_index(cls.native)
        blocks = re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;', cls.native)
        cls.blocks = {hashlib.sha256(block.encode()).hexdigest().upper(): block for block in blocks}

    def test_actual_driver_truth_and_dotted_ram_loads(self):
        self.assertEqual(self.result['driver_count'], 41)
        self.assertEqual(self.result['truth_inputs'], 304)
        self.assertEqual(self.result['bit_driver_counts'], [5, 5, 5, 5, 6, 6, 5, 4])
        self.assertEqual(self.result['maximum_local_load'], 24)
        self.assertEqual(self.result['predictor_local_primitive_input_loads']['fetch_index_30'], 10)
        print('PASS predictor native drivers=41 truth=304 maximum_local_load=24 dotted_ram_loads=10')

    def test_every_driver_truth_mutation(self):
        for index, record in enumerate(self.result['drivers']):
            block = self.blocks[record['cell_sha256']]
            match = re.search(r'\.INIT\((\d+)\x27b([01]+)\)', block)
            digits = match[2][:-1] + ('0' if match[2][-1] == '1' else '1')
            changed = block[:match.start(2)] + digits + block[match.end(2):]
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'XOR changed'):
                inspect_predictor_index(self.native.replace(block, changed))
            print('PASS predictor native truth rejection: ' + str(index))

    def test_every_driver_operand_mutation(self):
        for index, record in enumerate(self.result['drivers']):
            block = self.blocks[record['cell_sha256']]
            before = '.I1 (next_pc[2])' if record['bit'] == 0 else '.I1 (fetch_pc[' + str(10 + ((record['bit'] - 4) % 8)) + '])'
            self.assertEqual(block.count(before), 1)
            changed = block.replace(before, '.I1 (foreign_pc_bit)')
            with self.subTest(index=index), self.assertRaises(ValueError):
                inspect_predictor_index(self.native.replace(block, changed))
            print('PASS predictor native operand rejection: ' + str(index))

    def test_hierarchy_and_inventory_mutations(self):
        changes = [('alias', 'assign fetch_index_alias[0] = fetch_index[0];', 'assign fetch_index_alias[0] = fetch_index[1];')]
        for index in range(1, 5):
            before = '.fetch_index_' + str(index) + ' (' + chr(92) + 'predictor/fetch_index_' + str(index) + ' )'
            changes.append(('binding_' + str(index), before, before.replace('fetch_index_' + str(index) + ' )', 'fetch_index_foreign )')))
        block = self.blocks[self.result['drivers'][-1]['cell_sha256']]
        changes.extend([('missing_driver', block, ''), ('duplicate_driver', block, block + chr(10) + block)])
        for name, before, after in changes:
            self.assertEqual(self.native.count(before), 1)
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_predictor_index(self.native.replace(before, after))
            print('PASS predictor native structural rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
