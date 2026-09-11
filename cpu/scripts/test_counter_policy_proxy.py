import random
import unittest

from analyze_branch_history import LocalResolutionReplay, folded_index
from counter_policy_proxy import CounterPolicyReplay, POLICIES


class CounterPolicyProxyTests(unittest.TestCase):
    def test_all_transition_entries(self):
        expected = {'saturating':((0,0,1,2),(1,2,3,3)), 'weak_flip_strong':((0,0,0,2),(1,3,3,3)), 'taken_flip_strong':((0,0,1,2),(1,3,3,3)), 'not_taken_flip_strong':((0,0,0,2),(1,2,3,3))}
        self.assertEqual(POLICIES,expected)
        for name,table in expected.items():
            for taken in (0,1):
                for counter in range(4):
                    model = CounterPolicyReplay(name)
                    index = folded_index(0x100)
                    model.valid[index] = True
                    model.tags[index] = 0
                    model.targets[index] = 0x80
                    model.conditional[index] = True
                    model.history[index] = 5
                    model.counters[index][5] = counter
                    self.assertEqual(model.step(0x100,0x80,taken,1),0x80 if counter>=2 else 0x104)
                    self.assertEqual(model.counters[index][5],table[taken][counter])
                    self.assertEqual(model.history[index],2+taken)
                    self.assertEqual([value for slot,value in enumerate(model.counters[index]) if slot!=5],[1]*7)
        print('PASS policy transition entries=32')

    def test_standard_matches_independent_parent(self):
        rng = random.Random(99817)
        model,parent = CounterPolicyReplay(),LocalResolutionReplay(3)
        for trial in range(20000):
            pc = rng.randrange(16384)*4
            target = rng.randrange(16384)*4
            taken,conditional = rng.randrange(2),int(trial%9!=0)
            self.assertEqual(model.step(pc,target,taken,conditional),parent.step(pc,target,taken,conditional))
            self.assertEqual(model.__dict__ | {'transitions':None},parent.__dict__ | {'transitions':None})
        print('PASS standard independent state replay=20000')

    def test_allocation_and_type_change(self):
        for name in POLICIES:
            model = CounterPolicyReplay(name)
            index = folded_index(0x100)
            model.step(0x100,0x80,1,1)
            self.assertEqual(model.counters[index],[2]*8)
            self.assertEqual(model.history[index],1)
            model.step(0x100,0x200,0,0)
            self.assertEqual(model.counters[index],[1]*8)
            self.assertEqual(model.history[index],0)
            model.step(0x100,0x300,1,0)
            self.assertEqual(model.counters[index],[1]*8)
            self.assertEqual(model.history[index],0)
            model.step(0x100,0x80,0,1)
            self.assertEqual(model.counters[index],[1]*8)
            self.assertEqual(model.history[index],0)

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            CounterPolicyReplay('unknown')
        model = CounterPolicyReplay()
        for args in ((0x101,0x80,1,1),(0x100,0x81,1,1),(0x10000,0x80,1,1),(0x100,0x10000,1,1),(0x100,0x80,2,1),(0x100,0x80,1,2)):
            with self.subTest(args=args),self.assertRaises(ValueError):
                model.step(*args)
        print('PASS invalid policy inputs=7')


if __name__ == "__main__":
    unittest.main(verbosity=2)
