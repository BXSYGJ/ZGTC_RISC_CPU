import copy
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import test_loop_predictor_pending as pending
from load_use_profile import file_hash
from run_history_loop_changes import CHANGES
from run_history_proxy import RunHistoryReplay
import test_loop_predictor_address_single_bank as single

PROJECT = Path(__file__).resolve().parents[1]
CORE = PROJECT / 'experiments/run_history_loop_single/rv32_btb.sv'


class HybridReference(single.SingleBankReference):
    def cycle(self, reset, invalidate, fetch, valid, pc, target, taken, conditional):
        index = self.index(pc)
        previous = copy.deepcopy(self.base.get(index))
        legal = reset and not invalidate and valid and pc < (1 << self.address_bits) and target < (1 << self.address_bits) and pc % 4 == target % 4 == 0
        super().cycle(reset, invalidate, fetch, valid, pc, target, taken, conditional)
        if legal:
            allocated = previous is None or previous['tag'] != pc >> (self.index_bits + 2) or previous['conditional'] != conditional
            if allocated:
                self.base[index]['history'] = taken * 4 if conditional else 0
            elif conditional:
                history = previous['history']
                self.base[index]['history'] = taken * 4 + (min(3, (history & 3) + 1) if history >> 2 == taken else 0)
        return super().cycle(1, 0, fetch, 0, 0, 0, 0, 0)


class HybridLoopTests(single.SingleBankLoopTests):
    def simulate(self, index_bits=8, address_bits=16, hashed=1, mutation=None):
        with patch.object(pending, 'CORE', CORE), patch.object(pending, 'Reference', HybridReference), patch.object(pending, 'vectors', single.interleaved_vectors):
            return pending.PendingLoopRtlTests.simulate(self, index_bits, address_bits, hashed, mutation)

    def test_exact_pending_only_extension(self):
        parent = PROJECT / 'experiments/loop_predictor_address_single_bank/rv32_btb.sv'
        self.assertEqual(file_hash(parent), '09CFCC123BA4604C4F26C702213E53B6CABF6D76FFFFB21E0E30ADE1B4C7F7C7')
        self.assertEqual(file_hash(CORE), 'E0E22B053206C0C4610EC814FA71A1E86FF3EF09FF9124BE6DEA10BF4D720C74')
        source = CORE.read_text()
        for before, after in reversed(CHANGES):
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        self.assertEqual(source, parent.read_text())

    def test_base_state_matches_independent_history_model(self):
        model = HybridReference()
        reference = RunHistoryReplay('both_run_saturating')
        randomizer = random.Random(9741)
        for trial in range(8192):
            pc = randomizer.randrange(1, 16384) * 4
            target = randomizer.randrange(16384) * 4
            taken = randomizer.randrange(2)
            conditional = int(trial % 9 != 0)
            model.cycle(1, 0, pc, 1, pc, target, taken, conditional)
            reference.step(pc, target, taken, conditional)
            for index, entry in model.base.items():
                self.assertTrue(reference.valid[index])
                self.assertEqual(entry['tag'], reference.tags[index])
                self.assertEqual(entry['target'], reference.targets[index])
                self.assertEqual(entry['conditional'], reference.conditional[index])
                self.assertEqual(entry['history'], reference.history[index])
                self.assertEqual(entry['counters'], reference.counters[index])
        print('PASS hybrid RTL reference independent base-state replay=8192')

    def test_history_runtime_mutants(self):
        mutations = {
            'wrong_training_bank': ('history[update_index]==PATTERN_INDEX', 'history[update_index]!=PATTERN_INDEX'),
            'train_all_banks': ('history[update_index]==PATTERN_INDEX', "1'b1"),
            'wrong_direction': ('prior_history[HISTORY_BITS-1]==update_taken', 'prior_history[HISTORY_BITS-1]!=update_taken'),
            'missing_saturation': ('run_saturated ? prior_history', "1'b0 ? prior_history"),
            'frozen_history': ('history[update_index]<=next_history;', 'history[update_index]<=history[update_index];'),
            'shift_history': ('history[update_index]<=next_history;', 'history[update_index]<=(history[update_index] << 1) | update_taken;'),
            'wrong_initial_direction': ("{update_taken,{(HISTORY_BITS-1){1'b0}}} : {HISTORY_BITS{1'b0}}", "{{(HISTORY_BITS-1){1'b0}},update_taken} : {HISTORY_BITS{1'b0}}"),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                result, count, overrides = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL pending_loop', result.stdout + result.stderr)
                print('PASS hybrid history runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
