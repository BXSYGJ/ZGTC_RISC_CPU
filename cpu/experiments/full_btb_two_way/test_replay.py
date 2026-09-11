import unittest

from replay_conflicts import replay


class ConflictReplayTests(unittest.TestCase):
    def test_same_set_replacement_and_hits(self):
        stream = [(index, address, 0x6f) for index, address in enumerate((0, 20, 0, 40, 0, 20, 40))]
        result = replay(stream, index_bits=2)
        self.assertEqual(result["controls"], 7)
        self.assertEqual(result["direct_total_allocations"], 7)
        self.assertEqual(result["two_way_total_allocations"], 5)
        self.assertEqual(result["unique_control_pcs"], 3)

    def test_non_control_instructions_do_not_train(self):
        result = replay([(0, 0, 0x13), (1, 4, 0x33)])
        self.assertEqual(result["controls"], 0)
        self.assertEqual(result["two_way_total_allocations"], 0)

    def test_address_and_width_bounds(self):
        for address in (1, -4, 65536):
            with self.subTest(address=address), self.assertRaises(ValueError):
                replay([(0, address, 0x63)])
        for width in (0, 9):
            with self.subTest(width=width), self.assertRaises(ValueError):
                replay([], index_bits=width)


if __name__ == "__main__":
    unittest.main(verbosity=2)
