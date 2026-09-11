import copy
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import test_loop_predictor_pending as pending
from loop_single_bank_changes import CHANGES
from test_loop_predictor_small import Reference, vectors

PROJECT = Path(__file__).resolve().parents[1]
CORE = PROJECT / 'experiments/loop_predictor_single_bank/rv32_btb.sv'


class SingleBankReference(Reference):
    def cycle(self, reset, invalidate, fetch, valid, pc, target, taken, conditional):
        excluded = reset and not invalidate and valid and ((self.index(pc) >> 5) & 1)
        preserved = copy.deepcopy(self.loops) if excluded else None
        outputs = super().cycle(reset, invalidate, fetch, valid, pc, target, taken, conditional)
        if excluded:
            self.loops = preserved
            outputs = super().cycle(1, 0, fetch, 0, 0, 0, 0, 0)
        return outputs


def interleaved_vectors(index_bits=8, address_bits=16, hashed=1):
    rows = vectors(index_bits, address_bits, hashed)
    model = Reference(index_bits, address_bits, hashed)
    excluded = [pc for pc in range(0x100, 0x1000, 4) if (model.index(pc) >> 5) & 1]
    def emit(pc=0x514, target=0x504, taken=1, reset=1):
        inputs = (reset, 0, 0x514, 1, pc, target, taken, 1, 0, 0, 0)
        rows.append(' '.join(f'{value:x}' for value in inputs))
    if excluded:
        emit(reset=0)
        for repeat in range(6):
            for iteration in range(3):
                emit()
                emit(pc=excluded[0], target=excluded[0]-16)
            emit(taken=0)
    return rows


class SingleBankLoopTests(pending.PendingLoopRtlTests):
    def simulate(self, index_bits=8, address_bits=16, hashed=1, mutation=None):
        with patch.object(pending, 'CORE', CORE), patch.object(pending, 'Reference', SingleBankReference), patch.object(pending, 'vectors', interleaved_vectors):
            return super().simulate(index_bits, address_bits, hashed, mutation)

    def test_exact_pending_only_extension(self):
        parent = PROJECT / 'experiments/loop_predictor_pending/rv32_btb.sv'
        self.assertEqual(sha256(parent.read_bytes()).hexdigest().upper(), '74F4600463529ECA9520CD23D240AEAC75BB95B506932E4EB80544DFD8AEF896')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '13CE1849DE67455BBD212A6F35B21367F34127974A54EF1B2EA488D373989984')
        source = CORE.read_text()
        for before, after in reversed(CHANGES):
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        self.assertEqual(source, parent.read_text())

    def test_runtime_mutants(self):
        mutations = {
            'disabled_pending': ('loop_pending_taken ? loop_ahead_direction[loop_fetch_index]', "1'b0 ? loop_ahead_direction[loop_fetch_index]"),
            'wrong_ahead': ('loop_pending_taken ? loop_ahead_direction[loop_fetch_index]', 'loop_pending_taken ? !loop_ahead_direction[loop_fetch_index]'),
            'missing_valid': ('!invalidate && train_update && update_conditional', '!invalidate && update_conditional'),
            'missing_invalidate': ('!invalidate && train_update && update_conditional', 'train_update && update_conditional'),
            'missing_taken': ('train_update && update_conditional && update_taken &&', 'train_update && update_conditional &&'),
            'missing_conditional': ('train_update && update_conditional && update_taken &&', 'train_update && update_taken &&'),
            'missing_backward': ('update_target<update_pc && loop_update_match', 'loop_update_match'),
            'missing_update_match': ('update_target<update_pc && loop_update_match && loop_fetch_index==loop_update_index;', 'update_target<update_pc && loop_fetch_index==loop_update_index;'),
            'ahead_off_by_one': ("2'b10})<{1'b0,loop_trip[loop_update_index]}", "2'b01})<{1'b0,loop_trip[loop_update_index]}"),
            'ahead_overflow': ("({1'b0,loop_count[loop_update_index]}+{{(LOOP_COUNT_BITS-1){1'b0}},2'b10})<{1'b0,loop_trip[loop_update_index]}", "(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-2){1'b0}},2'b10})<loop_trip[loop_update_index]"),
            'missing_admission': ('else if (train_update && loop_update_admitted)', 'else if (train_update)'),
            'inverted_admission': ('loop_update_admitted=!update_index[LOOP_INDEX_SHIFT];', 'loop_update_admitted=update_index[LOOP_INDEX_SHIFT];'),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                result, count, overrides = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL pending_loop', result.stdout + result.stderr)
                print('PASS single-bank loop runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
