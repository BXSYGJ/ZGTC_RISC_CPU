import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from loop_pending_changes import CHANGES
from test_loop_predictor_small import Reference, vectors

PROJECT = Path(__file__).resolve().parents[1]
CORE = PROJECT / 'experiments/loop_predictor_pending/rv32_btb.sv'


def pending_vectors(index_bits=8, address_bits=16, hashed=1):
    reference = Reference(index_bits, address_bits, hashed)
    inputs_list = [tuple(int(value, 16) for value in row.split()[:8]) for row in vectors(index_bits, address_bits, hashed)]
    def emit(fetch=0x514, pc=0x514, target=0x504, taken=1, conditional=1, valid=1, reset=1, invalidate=0):
        inputs_list.append((reset, invalidate, fetch, valid, pc, target, taken, conditional))
    def warm(pc=0x514, trips=3):
        for repeat in range(5):
            for iteration in range(trips):
                emit(fetch=pc, pc=pc, target=pc-16)
            emit(fetch=pc, pc=pc, target=pc-16, taken=0)
    for trips in (1, 2, 3, 29, 31):
        emit(reset=0)
        warm(trips=trips)
        for repeat in range(3):
            for iteration in range(trips):
                emit()
            emit(taken=0)
    for overrides in ({'valid': 0}, {'invalidate': 1}, {'taken': 0}, {'conditional': 0},
                      {'target': 0x524}, {'pc': 0x515}, {'target': 0x505},
                      {'pc': 0x10514}, {'target': 0x10504}, {'reset': 0},
                      {'fetch': 0x515}, {'fetch': 0x10514}):
        emit(reset=0)
        warm()
        emit()
        emit()
        emit(**overrides)
    same_slot_pc = next(pc for pc in range(0x100, 0x1000, 4) if pc != 0x514 and (reference.index(pc) >> 5) & 1 == (reference.index(0x514) >> 5) & 1)
    emit(reset=0)
    warm()
    emit()
    emit()
    emit(pc=same_slot_pc, target=same_slot_pc-16)
    different_slot = [pc for pc in range(0x100, 0x1000, 4) if (reference.index(pc) >> 5) & 1 != (reference.index(0x514) >> 5) & 1]
    if different_slot:
        other_pc = different_slot[0]
        emit(reset=0)
        warm(pc=other_pc)
        warm()
        emit()
        emit()
        emit(pc=other_pc, target=other_pc-16)
    rows = []
    overrides = 0
    for inputs in inputs_list:
        reset, invalidate, fetch, valid, pc, target, taken, conditional = inputs
        if not reset:
            reference.base.clear()
            reference.loops.clear()
        before = reference.cycle(1, 0, fetch, 0, 0, 0, 0, 0)
        hit, predicted, destination = before
        loop = reference.loops.get((reference.index(fetch) >> 5) & 1)
        entry = reference.base.get(reference.index(fetch))
        legal = valid and pc < (1 << address_bits) and target < (1 << address_bits) and pc % 4 == target % 4 == 0
        if reset and not invalidate and legal and conditional and taken and target < pc and fetch == pc and hit and entry['conditional'] and loop is not None and loop['pc'] == fetch and loop['confidence'] >= 2:
            predicted = int(loop['count'] + 1 < loop['trip'])
            overrides += int(predicted != before[1])
        after = reference.cycle(*inputs)
        rows.append(' '.join(f'{value:x}' for value in inputs + (hit, predicted, destination) + after))
    if overrides < 30:
        raise AssertionError('Insufficient changed pending predictions')
    return rows, overrides


class PendingLoopRtlTests(unittest.TestCase):
    def simulate(self, index_bits=8, address_bits=16, hashed=1, mutation=None):
        source = CORE.read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='pending-loop-rtl-') as temporary:
            directory = Path(temporary)
            rtl = directory / 'rv32_btb.sv'
            rtl.write_text(source)
            data = directory / 'vectors.txt'
            rows, overrides = pending_vectors(index_bits, address_bits, hashed)
            data.write_text(chr(10).join(rows) + chr(10))
            image = directory / 'test.vvp'
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'loop_predictor_pending_tb',
                f'-Ploop_predictor_pending_tb.INDEX_BITS={index_bits}', f'-Ploop_predictor_pending_tb.ADDRESS_BITS={address_bits}',
                f'-Ploop_predictor_pending_tb.HASH_INDEX={hashed}', '-o', str(image), str(rtl), str(PROJECT / 'sim/loop_predictor_pending_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(['vvp', str(image), '+vectors=' + str(data)], capture_output=True, text=True, timeout=60)
            return result, len(rows), overrides

    def test_exact_pending_only_extension(self):
        parent = PROJECT / 'experiments/loop_predictor_small/rv32_btb.sv'
        self.assertEqual(sha256(parent.read_bytes()).hexdigest().upper(), '826199447568BB4D2BE0BF3D48CFF50E8393AE3EF722666EABA770BEDCC346E0')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '74F4600463529ECA9520CD23D240AEAC75BB95B506932E4EB80544DFD8AEF896')
        source = CORE.read_text()
        for before, after in reversed(CHANGES):
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        self.assertEqual(source, parent.read_text())

    def test_independent_pre_and_post_model(self):
        for index, address, hashed in ((8, 16, 1), (8, 32, 1), (8, 16, 0), (4, 32, 1), (1, 16, 1)):
            with self.subTest(index=index, address=address, hashed=hashed):
                result, count, overrides = self.simulate(index, address, hashed)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS pending_loop vectors={count} queries={count*2}', result.stdout)
                print(f'PASS pending loop model index={index} address={address} hash={hashed} vectors={count} queries={count*2} changed={overrides}')

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
            'missing_slot_match': ('loop_update_match && loop_fetch_index==loop_update_index;', 'loop_update_match;'),
            'ahead_off_by_one': ("2'b10})<{1'b0,loop_trip[loop_update_index]}", "2'b01})<{1'b0,loop_trip[loop_update_index]}"),
            'ahead_overflow': ("({1'b0,loop_count[loop_update_index]}+{{(LOOP_COUNT_BITS-1){1'b0}},2'b10})<{1'b0,loop_trip[loop_update_index]}", "(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-2){1'b0}},2'b10})<loop_trip[loop_update_index]"),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                result, count, overrides = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL pending_loop', result.stdout + result.stderr)
                print('PASS pending loop runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
