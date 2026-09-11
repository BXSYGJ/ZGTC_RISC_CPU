import random
import unittest

from analyze_branch_history import LocalResolutionReplay, folded_index
from folded_history_proxy import FoldedHistoryReplay, MODES


class FoldedHistoryProxyTests(unittest.TestCase):
    def test_exact_mapping_and_transition(self):
        checked = 0
        for mode in MODES:
            histories = range(8 if mode=='baseline3' else 16)
            for history in histories:
                expected_pattern = history
                if mode.startswith('fold4_'):
                    lane = {'fold4_low':1,'fold4_middle':2,'fold4_high':4}[mode]
                    expected_pattern = (history%8) ^ (lane if history>=8 else 0)
                for taken in (0,1):
                    for counter in range(4):
                        model = FoldedHistoryReplay(mode)
                        index = folded_index(0x100)
                        model.valid[index] = True
                        model.tags[index] = 0
                        model.targets[index] = 0x80
                        model.conditional[index] = True
                        model.history[index] = history
                        model.counters[index][expected_pattern] = counter
                        self.assertEqual(model.pattern(history),expected_pattern)
                        self.assertEqual(model.step(0x100,0x80,taken,1),0x80 if counter>=2 else 0x104)
                        self.assertEqual(model.counters[index][expected_pattern],min(3,counter+1) if taken else max(0,counter-1))
                        self.assertEqual(model.history[index],(history*2+taken)%len(histories))
                        self.assertEqual([value for slot,value in enumerate(model.counters[index]) if slot!=expected_pattern],[1]*(model.patterns-1))
                        checked += 1
        self.assertEqual(checked,576)
        print('PASS folded history mapping and transitions=576')

    def test_baseline_matches_independent_parent(self):
        model,parent = FoldedHistoryReplay(),LocalResolutionReplay(3)
        rng = random.Random(61723)
        for trial in range(20000):
            pc,target = rng.randrange(16384)*4,rng.randrange(16384)*4
            taken,conditional = rng.randrange(2),int(trial%13!=0)
            self.assertEqual(model.step(pc,target,taken,conditional),parent.step(pc,target,taken,conditional))
            for field in ('valid','tags','targets','conditional','history','counters'):
                self.assertEqual(getattr(model,field),getattr(parent,field))
        print('PASS folded baseline independent state replay=20000')

    def test_allocation_and_invalid_mode(self):
        for mode in MODES:
            model = FoldedHistoryReplay(mode)
            index = folded_index(0x100)
            model.step(0x100,0x80,1,1)
            self.assertEqual(model.counters[index],[2]*model.patterns)
            self.assertEqual(model.history[index],1)
            model.step(0x100,0x200,0,0)
            self.assertEqual(model.counters[index],[1]*model.patterns)
            self.assertEqual(model.history[index],0)
            with self.assertRaises(ValueError):
                model.pattern(1 << model.width)
        with self.assertRaises(ValueError):
            FoldedHistoryReplay('unknown')


if __name__ == "__main__":
    unittest.main(verbosity=2)
