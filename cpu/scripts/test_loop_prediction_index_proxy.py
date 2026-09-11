import random
import unittest

from loop_prediction_proxy import LoopResolutionProxy
from loop_prediction_index_proxy import IndexedLoopResolutionProxy


class IndexedLoopProxyTests(unittest.TestCase):
    def test_zero_shift_exact_parent_replay(self):
        for entries in (1, 2, 4, 8, 16):
            for bits in (5, 8):
                parent = LoopResolutionProxy(entries, 2, bits)
                candidate = IndexedLoopResolutionProxy(entries, 2, bits, 0)
                randomizer = random.Random(913 + entries + bits)
                for vector in range(8192):
                    pc = randomizer.randrange(1, 256) * 4
                    target = randomizer.randrange(256) * 4
                    taken = randomizer.randrange(2)
                    conditional = randomizer.randrange(2)
                    self.assertEqual(candidate.step(pc, target, taken, conditional), parent.step(pc, target, taken, conditional))
                self.assertEqual(candidate.entries, parent.entries)
                self.assertEqual(candidate.overrides, parent.overrides)
                self.assertEqual(candidate.prediction_changes, parent.prediction_changes)

    def test_shift_changes_conflict_not_branch_tag(self):
        model = IndexedLoopResolutionProxy(entries=2, index_shift=1)
        for pc in (0x100, 0x104):
            model.step(pc, pc - 4, 1, 1)
        self.assertEqual(sum(entry is not None for entry in model.entries), 1)
        self.assertEqual(next(entry for entry in model.entries if entry)['pc'], 0x104)
        model.step(0x108, 0x104, 1, 1)
        self.assertEqual(sum(entry is not None for entry in model.entries), 2)

    def test_index_range_rejections(self):
        for entries, shift in ((2, 8), (4, 7), (8, 6), (16, 5), (4, -1), (4, True)):
            with self.subTest(entries=entries, shift=shift), self.assertRaises(ValueError):
                IndexedLoopResolutionProxy(entries=entries, index_shift=shift)


if __name__ == '__main__':
    unittest.main(verbosity=2)
