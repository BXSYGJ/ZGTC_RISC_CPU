import struct
import tempfile
import unittest
from pathlib import Path

from load_use_profile import RECORD, compare_records, dependency_kind, extract_cycle_pc, firmware_image, instruction_info, trace_records


def instruction(opcode, destination=0, first=0, second=0, funct3=0, funct7=0):
    return opcode | destination << 7 | funct3 << 12 | first << 15 | second << 20 | funct7 << 25


class LoadUseProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.load = instruction(3, destination=5, first=6, funct3=2)
        self.add = instruction(0x33, destination=7, first=5, second=8)
        self.start = 0xb00022f3
        self.stop = 0xb0002373
        self.image = b''.join(struct.pack('<I', word) for word in (self.start, self.load, self.add, self.stop))
        self.records = [(10, 0, self.start), (12, 4, self.load), (13, 8, self.add), (16, 12, self.stop)]
        self.metadata = dict(schema=1, record_bytes=16, records=4, start_pc=0, stop_pc=12, start_cycle=10, stop_cycle=16, cycles=6)

    def read_trace(self, records=None, metadata=None, suffix=b''):
        path = self.root / 'trace.bin'
        path.write_bytes(b''.join(RECORD.pack(*record) for record in (self.records if records is None else records)) + suffix)
        return list(trace_records(path, self.metadata if metadata is None else metadata, self.image))

    def test_firmware_image(self):
        path = self.root / 'firmware.hex'
        path.write_text('12345678\n' * 16384, encoding='ascii')
        self.assertEqual(firmware_image(path), b'\x78\x56\x34\x12' * 16384)
        for text in ('12345678\n', 'xxxxxxxx\n' * 16384, '1234567\n' * 16384):
            path.write_text(text, encoding='ascii')
            with self.assertRaises(ValueError):
                firmware_image(path)

    def test_timer_boundary(self):
        disassembly = '00000000 <start_time>:\n   0: b00022f3 csrr t0,mcycle\n'
        self.assertEqual(extract_cycle_pc(disassembly, self.image, 'start_time'), 0)
        bad_inputs = [disassembly.replace('start_time', 'wrong'), disassembly + disassembly,
                      disassembly.replace('b00022f3', 'b80022f3'), disassembly.replace('b00022f3', 'b0002373'),
                      disassembly.replace('   0:', '   2:'), disassembly.replace('   0:', '  40:'),
                      disassembly + '0000000c <stop_time>:\n   c: b0002373 csrr t1,mcycle\n',
                      '00000000 <start_time>:\n0000000c <other>:\n   c: b0002373 csrr t1,mcycle\n']
        for text in bad_inputs:
            with self.subTest(text=text), self.assertRaises(ValueError):
                extract_cycle_pc(text, self.image, 'start_time')

    def test_source_use_and_categories(self):
        cases = [(0x13, 0, 0, 'integer_add_sub', 1), (0x33, 0, 32, 'integer_add_sub', 3),
                 (0x33, 1, 0, 'integer_shift', 3), (0x33, 2, 0, 'integer_compare', 3),
                 (0x33, 7, 0, 'integer_logic', 3), (0x33, 3, 1, 'multiply', 3),
                 (0x33, 4, 1, 'divide', 3), (0x63, 0, 0, 'branch_compare', 3),
                 (0x67, 0, 0, 'jalr_address', 1), (0x03, 2, 0, 'load_address', 1),
                 (0x73, 2, 0, 'csr_register', 1)]
        for opcode, funct3, funct7, category, mask in cases:
            consumer = instruction(opcode, first=5, second=5, funct3=funct3, funct7=funct7)
            with self.subTest(opcode=opcode, funct3=funct3, funct7=funct7):
                self.assertEqual(dependency_kind(self.load, consumer), (category, mask))
        for opcode, funct3 in ((0x37, 0), (0x17, 0), (0x6f, 0), (0x73, 6), (0x0f, 0)):
            self.assertEqual(dependency_kind(self.load, instruction(opcode, first=5, second=5, funct3=funct3)),
                             ('no_adjacent_load_dependency', 0))
        self.assertEqual(dependency_kind(instruction(3, funct3=2), instruction(0x33)), ('no_adjacent_load_dependency', 0))
        self.assertEqual(dependency_kind(self.add, self.add), ('no_adjacent_load_dependency', 0))

    def test_store_operand_roles(self):
        for first, second, name, mask in ((5, 6, 'store_address', 1), (6, 5, 'store_data', 2), (5, 5, 'store_address_data', 3)):
            self.assertEqual(dependency_kind(self.load, instruction(0x23, first=first, second=second, funct3=2)), (name, mask))

    def test_load_width_and_destination(self):
        for funct3 in (0, 1, 2, 4, 5):
            for destination in range(32):
                load = instruction(3, destination=destination, first=7, funct3=funct3)
                self.assertEqual(instruction_info(load), ('load_address', 7, None, destination))

    def test_illegal_decode(self):
        bad = [0, 0xffffffff, instruction(0x67, funct3=1), instruction(0x63, funct3=2),
               instruction(3, funct3=3), instruction(0x23, funct3=3), instruction(0x33, funct7=2),
               instruction(0x33, funct3=7, funct7=32), instruction(0x13, funct3=1, funct7=32),
               instruction(0x13, funct3=5, funct7=1), instruction(0x73, funct3=4), 0x10200073,
               instruction(0x0f, funct3=2)]
        for word in bad:
            with self.subTest(word=word), self.assertRaises(ValueError):
                instruction_info(word)

    def test_valid_trace(self):
        self.assertEqual(self.read_trace(), self.records)

    def test_trace_length_and_schema(self):
        for change in ({'schema': 2}, {'record_bytes': 8}, {'records': 3}, {'records': 0}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read_trace(metadata=dict(self.metadata, **change))
        with self.assertRaises(ValueError):
            self.read_trace(suffix=b'X')
        with self.assertRaises(ValueError):
            self.read_trace(records=[])

    def test_trace_content_and_boundaries(self):
        for index, record in ((1, (10, 4, self.load)), (1, (9, 4, self.load)),
                              (1, (12, 2, self.load)), (1, (12, 16, self.load)),
                              (1, (12, 4, self.add)), (1, (12, 0, self.start)),
                              (1, (12, 12, self.stop)), (0, (10, 4, self.load)),
                              (3, (16, 8, self.add))):
            records = list(self.records)
            records[index] = record
            with self.subTest(index=index, record=record), self.assertRaises(ValueError):
                self.read_trace(records=records)
        for change in ({'start_cycle': 9}, {'stop_cycle': 17}, {'cycles': 7}, {'start_pc': 4}, {'stop_pc': 8}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read_trace(metadata=dict(self.metadata, **change))

    def test_gap_accounting_includes_negative_compensation(self):
        candidate = [(100, 0, self.start), (102, 4, self.load), (104, 8, self.add), (106, 12, self.stop)]
        result = compare_records(iter(self.records), iter(candidate))
        dependency = result['groups']['integer_add_sub']
        independent = result['groups']['no_adjacent_load_dependency']
        self.assertEqual((dependency['intervals'], dependency['delta_cycles'], dependency['delta_histogram']), (1, 1, {1: 1}))
        self.assertEqual(independent['delta_histogram'], {-1: 1, 0: 1})
        self.assertEqual(sum(group['delta_cycles'] for group in result['groups'].values()), 0)
        self.assertEqual(sum(group['baseline_cycles'] for group in result['groups'].values()), 6)
        self.assertEqual(sum(group['candidate_cycles'] for group in result['groups'].values()), 6)
        self.assertEqual(result['records'], 4)
        self.assertEqual(result['transitions'][0]['consumer_pc'], 8)

    def test_sequence_mismatch_and_no_truncation(self):
        for candidate in (self.records[:-1], self.records + [self.records[-1]], [],
                          [(10, 0, self.start), (12, 4, self.add)] + self.records[2:],
                          [self.records[0], (10, 4, self.load)] + self.records[2:]):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                compare_records(iter(self.records), iter(candidate))
        with self.assertRaises(ValueError):
            compare_records([], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

