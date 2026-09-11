import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from test_loop_predictor_pending import pending_vectors

PROJECT = Path(__file__).resolve().parents[1]
CORE = PROJECT / 'experiments/loop_predictor_pending_pc_slice/rv32_btb.sv'


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

    def test_exact_pending_pc_match(self):
        parent = PROJECT / 'experiments/loop_predictor_pending_pc_match/rv32_btb.sv'
        self.assertEqual(sha256(parent.read_bytes()).hexdigest().upper(), '97D0E8FB6FBB695AD44533A1530632528CCEB0FC1555422986110061BB466686')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '419D7806693078300353A494C96041045B0A0DA51F4066B0280D2DCE840F266B')
        source = CORE.read_text()
        after = 'update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];'
        before = 'update_target<update_pc && fetch_pc==update_pc;'
        self.assertEqual(source.count(after), 1)
        self.assertEqual(source.replace(after,before),parent.read_text())

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
            'missing_backward': ('update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];', 'fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];'),
            'missing_pc_match': ('update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];', 'update_target<update_pc;'),
            'wrong_pc_match': ('update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]==update_pc[ADDRESS_BITS-1:2];', 'update_target<update_pc && fetch_pc[ADDRESS_BITS-1:2]!=update_pc[ADDRESS_BITS-1:2];'),
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
