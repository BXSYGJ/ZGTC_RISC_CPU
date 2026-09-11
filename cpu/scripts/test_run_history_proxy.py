import random
import unittest

from analyze_branch_history import LocalResolutionReplay, folded_index
from run_history_proxy import RunHistoryReplay, MODES


class RunHistoryProxyTests(unittest.TestCase):
    def test_exhaustive_state_transitions(self):
        tables = {'baseline3':((0,2,4,6,0,2,4,6),(1,3,5,7,1,3,5,7)), 'taken_run_saturating':((0,0,0,0,0,0,0,0),(1,2,3,4,5,6,7,7)), 'taken_run_modulo':((0,0,0,0,0,0,0,0),(1,2,3,4,5,6,7,0)), 'both_run_saturating':((1,2,3,3,0,0,0,0),(4,4,4,4,5,6,7,7))}
        self.assertEqual(set(MODES),set(tables))
        for mode,table in tables.items():
            for taken in (0,1):
                for history in range(8):
                    model = RunHistoryReplay(mode)
                    self.assertEqual(model.advance(history,taken),table[taken][history])
                    index = folded_index(0x100)
                    model.valid[index] = True
                    model.tags[index] = 0
                    model.targets[index] = 0x80
                    model.conditional[index] = True
                    model.history[index] = history
                    model.counters[index][history] = 2
                    self.assertEqual(model.step(0x100,0x80,taken,1),0x80)
                    self.assertEqual(model.history[index],table[taken][history])
                    self.assertEqual(model.counters[index][history],3 if taken else 1)
        print('PASS run history transitions and selected bank=64')

    def test_baseline_matches_independent_parent(self):
        model,parent = RunHistoryReplay(),LocalResolutionReplay(3)
        rng = random.Random(17891)
        for trial in range(20000):
            args = (rng.randrange(16384)*4,rng.randrange(16384)*4,rng.randrange(2),int(trial%11!=0))
            self.assertEqual(model.step(*args),parent.step(*args))
            for field in ('valid','tags','targets','conditional','history','counters'):
                self.assertEqual(getattr(model,field),getattr(parent,field))
        print('PASS run baseline independent state replay=20000')

    def test_initialization_and_invalid_mode(self):
        for mode in MODES:
            for taken in (0,1):
                model = RunHistoryReplay(mode)
                index = folded_index(0x100)
                model.step(0x100,0x80,taken,1)
                self.assertEqual(model.history[index],taken*4 if mode=='both_run_saturating' else taken)
                self.assertEqual(model.counters[index],[2 if taken else 1]*8)
                model.step(0x100,0x200,1,0)
                self.assertEqual(model.history[index],0)
        with self.assertRaises(ValueError):
            RunHistoryReplay('unknown')


if __name__ == "__main__":
    unittest.main(verbosity=2)
