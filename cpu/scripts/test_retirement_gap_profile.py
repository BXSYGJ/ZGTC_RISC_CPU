import unittest

from retirement_gap_profile import summarize_records


class RetirementGapProfileTests(unittest.TestCase):
    def test_partition_and_noncausal_scope(self):
        records = [(10, 0, 0xb00022f3), (12, 4, 0x00032283), (13, 8, 0x00528463),
                   (17, 16, 0x0000006f), (18, 20, 0xb0002373)]
        result = summarize_records(records)
        self.assertEqual((result['cycles'], result['intervals'], result['extra_cycles_above_one_per_interval']), (8, 4, 4))
        self.assertEqual(result['axes']['adjacent_load_dependency']['branch_compare']['intervals'], 1)
        self.assertEqual(result['axes']['adjacent_load_dependency']['branch_compare']['extra_cycles_above_one_per_interval'], 0)
        self.assertEqual(result['axes']['preceding_control']['branch']['extra_cycles_above_one_per_interval'], 3)
        self.assertIn('not_internal_stall', result['scope'])
        for groups in result['axes'].values():
            self.assertEqual(sum(group['cycles'] for group in groups.values()), 8)
            self.assertEqual(sum(group['extra_cycles_above_one_per_interval'] for group in groups.values()), 4)

    def test_repeated_transition_histogram_and_order(self):
        records = [(0, 0, 0x00000013), (1, 4, 0x00000013), (3, 0, 0x00000013), (7, 4, 0x00000013)]
        result = summarize_records(iter(records))
        first = result['transitions'][0]
        self.assertEqual((first['producer_pc'], first['consumer_pc']), (0, 4))
        self.assertEqual(first['gap_histogram'], {1: 1, 4: 1})
        self.assertEqual(first['extra_cycles_above_one_per_interval'], 3)
        self.assertEqual(first['max_gap'], 4)

    def test_rejects_bad_records_and_nonmonotonic_cycles(self):
        cases = [[], [(0, 0, 0x13)], [(0, 0, 0x13), (0, 4, 0x13)],
                 [(1, 0, 0x13), (0, 4, 0x13)], [(False, 0, 0x13), (1, 4, 0x13)],
                 [(0, 0, 0x13), (1, 2, 0x13)], [(0, 0, 0x13), (1, 65536, 0x13)],
                 [(0, 0, 0x13), (1, 4, 0xffffffff)]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(ValueError):
                summarize_records(records)

    def test_rejects_mutated_instruction_at_repeated_transition(self):
        with self.assertRaisesRegex(ValueError, 'Instruction changed'):
            summarize_records([(0, 0, 0x13), (1, 4, 0x13), (2, 0, 0x13), (3, 4, 0x00100013)])

    def test_streaming_sequence_digest_is_timing_independent(self):
        baseline = summarize_records([(0, 0, 0x13), (1, 4, 0x13)])
        slower = summarize_records([(10, 0, 0x13), (15, 4, 0x13)])
        self.assertEqual(baseline['instruction_sequence_sha256'], slower['instruction_sequence_sha256'])
        self.assertNotEqual(baseline['cycles'], slower['cycles'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
