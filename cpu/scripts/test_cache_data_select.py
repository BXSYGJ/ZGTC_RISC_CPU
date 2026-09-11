import itertools
import unittest

import test_cache_lru_storage as lru_tests


class CacheDataSelectTests(lru_tests.CacheLruStorageTests):
    def candidate_path(self):
        return lru_tests.PROJECT / 'experiments/cache_data_select/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        if reference_only:
            return miter
        monitor = '''    generate if(READONLY==0) begin : data_select_equivalence
        wire original_forward=exercised.cache.hit1 ?
            exercised.cache.synchronous_writable.forward_way1 : exercised.cache.synchronous_writable.forward_way0;
        wire [31:0] original_word=exercised.cache.hit1 ?
            (exercised.cache.synchronous_writable.forward_way1 ? exercised.cache.synchronous_writable.forward_data : exercised.cache.synchronous_writable.read_way1) :
            (exercised.cache.synchronous_writable.forward_way0 ? exercised.cache.synchronous_writable.forward_data : exercised.cache.synchronous_writable.read_way0);
        always @(posedge exercised.clk) if(exercised.rst_n && exercised.cache.state==1 && (exercised.cache.hit0 || exercised.cache.hit1)) begin
            check(exercised.cache.current_word===original_word,"flattened data selection equals original nested mux");
            check(exercised.cache.synchronous_writable.read_forward===original_forward,"forward selection equals selected way flag");
            check((exercised.cache.synchronous_writable.read_select0 +
                {1'b0,exercised.cache.synchronous_writable.read_select1} +
                {1'b0,exercised.cache.synchronous_writable.read_forward})==2'd1,"data selection is exactly one hot");
        end
    end endgenerate
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_writable_geometry_forwarding(self):
        for bits, set_bits, fast_read, fast_write, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                result = self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read,
                                       fast_write=fast_write, overlap=overlap,
                                       geometry=1, synchronous_coverage=True)
                self.require_pass(result)
                self.assertIn('SYNC_WRITE forward0=', result.stdout)
        print('PASS32 writable data selection, forward, byte merge and stalled writeback configurations')

    def test_compiled_data_select_mutations(self):
        mutations = (
            ('read_select0=!hit1 && !forward_way0', 'read_select0=hit1 && !forward_way0'),
            ('read_select1=hit1 && !forward_way1', 'read_select1=!hit1 && !forward_way1'),
            ('read_select0=!hit1 && !forward_way0', 'read_select0=!hit1'),
            ('read_select1=hit1 && !forward_way1', 'read_select1=hit1'),
            ('read_forward=hit1 ? forward_way1 : forward_way0', 'read_forward=hit1 ? forward_way0 : forward_way1'),
            ('read_forward=hit1 ? forward_way1 : forward_way0', "read_forward=1'b0"),
            ('(read_way0 & {32{read_select0}})', '(read_way1 & {32{read_select0}})'),
            ('(read_way1 & {32{read_select1}})', '(read_way0 & {32{read_select1}})'),
            ('(forward_data & {32{read_forward}})', '(read_way0 & {32{read_forward}})'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Mutation must fail a functional assertion')
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS nine compiled data-selection functional mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
