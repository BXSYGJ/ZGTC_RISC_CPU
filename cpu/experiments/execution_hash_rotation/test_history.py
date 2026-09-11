import random
import unittest

from screen_history import FoldedHistoryReplay
from screen_rotations import RotatedReplay


class HistoryTests(unittest.TestCase):
    def test_bank_truth_table(self):
        for fold in range(8):
            model = FoldedHistoryReplay(fold)
            for history in range(16):
                expected = sum((((history >> bit) & 1) ^ (((history >> 3) & 1) & ((fold >> bit) & 1))) << bit for bit in range(3))
                self.assertEqual(model.bank(history), expected)

    def test_baseline_predictions_and_state(self):
        reference = RotatedReplay(4)
        candidate = FoldedHistoryReplay(0)
        randomizer = random.Random(90363)
        for ordinal in range(20000):
            pc = randomizer.randrange(256) * 4
            target = randomizer.randrange(256) * 4
            taken = randomizer.randrange(2)
            conditional = randomizer.randrange(2)
            self.assertEqual(reference.step(pc, target, taken, conditional), candidate.step(pc, target, taken, conditional))
            for field in ("valid", "tags", "targets", "conditional", "counters"):
                self.assertEqual(getattr(reference, field), getattr(candidate, field))
            self.assertEqual(reference.history, [history & 7 for history in candidate.history])

    def test_invalid_fold(self):
        for fold in (-1, 8, True, 1.0, "1"):
            with self.assertRaises(ValueError):
                FoldedHistoryReplay(fold)


if __name__ == "__main__":
    unittest.main(verbosity=2)

