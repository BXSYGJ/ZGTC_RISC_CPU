import unittest

from screen_counter import CounterReplay


class CounterTests(unittest.TestCase):
    def test_transition_truth_tables(self):
        for mode in ("saturating", "hysteresis", "fast"):
            model = CounterReplay(mode)
            for state in range(4):
                for taken in range(2):
                    if mode == "saturating":
                        expected = min(3, state + 1) if taken else max(0, state - 1)
                    elif mode == "hysteresis":
                        expected = (3 if taken else 0) if state in (1, 2) else (state if taken == int(state >= 2) else (2 if state == 3 else 1))
                    else:
                        expected = (3 if state >= 2 else 2) if taken else (0 if state < 2 else 1)
                    self.assertEqual(model.transition(state, taken), expected)
                    self.assertEqual(model.transition(3 - state, 1 - taken), 3 - expected)

    def test_allocations(self):
        for mode in ("saturating", "hysteresis", "fast", "saturating_strong", "hysteresis_strong", "fast_strong"):
            for taken in range(2):
                model = CounterReplay(mode)
                self.assertEqual(model.step(0, 128, taken, 1), 4)
                expected = (3 if taken else 0) if mode.endswith("_strong") else (2 if taken else 1)
                self.assertEqual(model.counters[0], [expected] * 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)

