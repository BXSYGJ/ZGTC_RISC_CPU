import unittest

from analyze_branch_history import LocalResolutionReplay, folded_index
from loop_prediction_proxy import LoopResolutionProxy


class LoopPredictionProxyTests(unittest.TestCase):
    def train_loop(self, model, trips=4, repeats=4, pc=0x100, target=0x80):
        for repeat in range(repeats):
            for iteration in range(trips):
                model.step(pc, target, 1, 1)
            model.step(pc, target, 0, 1)

    def test_stable_loop_exit_and_direction(self):
        model = LoopResolutionProxy(entries=4, confidence_threshold=2)
        self.train_loop(model)
        for iteration in range(4):
            self.assertEqual(model.step(0x100, 0x80, 1, 1), 0x80)
        self.assertEqual(model.step(0x100, 0x80, 0, 1), 0x104)
        self.assertGreater(model.overrides, 0)
        self.assertGreater(model.prediction_changes, 0)

    def test_no_override_before_confidence(self):
        model = LoopResolutionProxy(confidence_threshold=3)
        baseline = LocalResolutionReplay(3)
        for taken in (1, 1, 0, 1, 1, 1, 0):
            self.assertEqual(model.step(0x100, 0x80, taken, 1), baseline.step(0x100, 0x80, taken, 1))
        self.assertEqual(model.overrides, 0)

    def test_changed_trip_and_overflow_remove_confidence(self):
        model = LoopResolutionProxy(entries=1, count_bits=3)
        self.train_loop(model, trips=3)
        for iteration in range(5):
            model.step(0x100, 0x80, 1, 1)
        model.step(0x100, 0x80, 0, 1)
        self.assertEqual(model.entries[0]['confidence'], 0)
        self.assertEqual(model.entries[0]['previous_trip'], 5)
        for iteration in range(8):
            model.step(0x100, 0x80, 1, 1)
        self.assertTrue(model.entries[0]['overflow'])
        model.step(0x100, 0x80, 0, 1)
        self.assertIsNone(model.entries[0]['previous_trip'])
        self.assertFalse(model.entries[0]['overflow'])

    def test_collision_does_not_reuse_other_branch_count(self):
        model = LoopResolutionProxy(entries=1)
        self.train_loop(model)
        model.step(0x200, 0x180, 1, 1)
        self.assertEqual(model.entries[0]['pc'], 0x200)
        self.assertEqual(model.entries[0]['current'], 1)
        self.assertIsNone(model.entries[0]['previous_trip'])
        self.assertEqual(model.entries[0]['confidence'], 0)

    def test_requires_actual_btb_hit_before_override(self):
        model = LoopResolutionProxy()
        self.train_loop(model)
        model.base.valid[folded_index(0x100)] = False
        before = model.overrides
        self.assertEqual(model.step(0x100, 0x80, 1, 1), 0x104)
        self.assertEqual(model.overrides, before)

    def test_forward_and_unconditional_use_parent_prediction(self):
        model = LoopResolutionProxy()
        baseline = LocalResolutionReplay(3)
        for pc, target, conditional in ((0x100, 0x180, 1), (0x200, 0x80, 0)):
            for taken in (1, 0, 1, 1):
                self.assertEqual(model.step(pc, target, taken, conditional), baseline.step(pc, target, taken, conditional))
        self.assertTrue(all(entry is None for entry in model.entries))

    def test_parameter_and_address_rejections(self):
        for keywords in ({'entries': 3}, {'entries': True}, {'confidence_threshold': 0}, {'count_bits': 1}):
            with self.subTest(keywords=keywords), self.assertRaises(ValueError):
                LoopResolutionProxy(**keywords)
        for values in ((2, 0, 1, 1), (65536, 0, 1, 1), (0x100, 0x80, 2, 1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                LoopResolutionProxy().step(*values)


if __name__ == '__main__':
    unittest.main(verbosity=2)
