import copy
import random
import unittest

from analyze_branch_history import folded_index
from loop_prediction_index_proxy import IndexedLoopResolutionProxy
from run_history_loop_proxy import RunHistoryLoopProxy
from run_history_proxy import RunHistoryReplay


class RunHistoryLoopProxyTests(unittest.TestCase):
    def test_baseline_preserves_independent_parent(self):
        candidate = RunHistoryLoopProxy('baseline3')
        parent = IndexedLoopResolutionProxy(2, 2, 5, 5)
        randomizer = random.Random(98427)
        for trial in range(20000):
            pc = randomizer.randrange(1, 16384) * 4
            target = randomizer.randrange(16384) * 4
            taken = randomizer.randrange(2)
            conditional = int(trial % 11 != 0)
            arguments = (pc, target, taken, conditional)
            self.assertEqual(candidate.step(*arguments), parent.step(*arguments))
            self.assertEqual(candidate.entries, parent.entries)
            for field in ('valid', 'tags', 'targets', 'conditional', 'history', 'counters'):
                self.assertEqual(getattr(candidate.base, field), getattr(parent.base, field))
        self.assertEqual(candidate.overrides, parent.overrides)
        self.assertEqual(candidate.prediction_changes, parent.prediction_changes)
        print('PASS hybrid baseline independent full-state replay=20000')

    def test_history_and_loop_training_remain_independent(self):
        candidate = RunHistoryLoopProxy()
        history = RunHistoryReplay('both_run_saturating')
        loops = IndexedLoopResolutionProxy(2, 2, 5, 5)
        randomizer = random.Random(46381)
        resolutions = 0
        expected_overrides = 0
        for episode in range(360):
            pc = (randomizer.randrange(1, 16384) * 4)
            target = pc - 4
            length = (1, 2, 3, 5, 17, 31, 32, 36, 0)[episode % 9]
            for iteration in range(7):
                for offset in range(length + 1):
                    taken = int(offset < length)
                    index = folded_index(pc)
                    slot = (index >> 5) & 1
                    entry = copy.deepcopy(loops.entries[slot])
                    hit = history.valid[index] and history.tags[index] == pc >> 10 and history.conditional[index]
                    prior_target = history.targets[index]
                    expected = history.step(pc, target, taken, 1)
                    if entry is not None and entry['pc'] == pc and hit and not entry['overflow'] and entry['previous_trip'] is not None and entry['confidence'] >= 2:
                        expected = prior_target if entry['current'] < entry['previous_trip'] else pc + 4
                        expected_overrides += 1
                    self.assertEqual(candidate.step(pc, target, taken, 1), expected)
                    loops.step(pc, target, taken, 1)
                    self.assertEqual(candidate.entries, loops.entries)
                    for field in ('valid', 'tags', 'targets', 'conditional', 'history', 'counters'):
                        self.assertEqual(getattr(candidate.base, field), getattr(history, field))
                    resolutions += 1
        self.assertGreater(expected_overrides, 0)
        self.assertEqual(candidate.overrides, expected_overrides)
        print('PASS hybrid independent history and loop resolutions=' + str(resolutions) + ' overrides=' + str(expected_overrides))

    def test_all_base_updates_survive_query_mask(self):
        model = RunHistoryLoopProxy()
        history = RunHistoryReplay('both_run_saturating')
        seen = set()
        for trial in range(4096):
            pc = ((trial * 127) % 16383 + 1) * 4
            bank = (folded_index(pc) >> 5) & 1
            seen.add(bank)
            arguments = (pc, pc - 4, int(trial % 3 != 0), int(trial % 7 != 0))
            model.step(*arguments)
            history.step(*arguments)
            self.assertEqual(model.base.history, history.history)
            self.assertEqual(model.base.counters, history.counters)
        self.assertEqual(seen, {0, 1})
        with self.assertRaises(ValueError):
            RunHistoryLoopProxy('unknown')
        print('PASS hybrid unmasked base updates=4096 banks=2')


if __name__ == '__main__':
    unittest.main(verbosity=2)
