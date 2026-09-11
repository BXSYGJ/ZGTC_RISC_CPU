import random
import unittest
from screen_rotations import LocalResolutionReplay, RotatedReplay, folded_index


class RotationTests(unittest.TestCase):
    def test_all_index_bits(self):
        for rotation in range(8):
            for high in range(256):
                rotated = int((f"{high:08b}" * 2)[rotation:rotation+8], 2)
                for low in (0, 1, 127, 255):
                    self.assertEqual(folded_index((high << 10) | (low << 2), rotation), rotated ^ low)

    def test_original_model_full_state(self):
        generator = random.Random(90210)
        original = LocalResolutionReplay(3)
        candidate = RotatedReplay(4)
        for step in range(20000):
            pc = generator.randrange(16384) * 4
            target = generator.randrange(16384) * 4
            taken = generator.randrange(2)
            conditional = generator.randrange(2)
            self.assertEqual(original.step(pc, target, taken, conditional), candidate.step(pc, target, taken, conditional))
            for field in ("valid", "tags", "targets", "conditional", "history", "counters"):
                self.assertEqual(getattr(original, field), getattr(candidate, field))

    def test_invalid_rotation(self):
        for value in (-1, 8, True, 4.0, "4"):
            with self.assertRaises(ValueError):
                RotatedReplay(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
