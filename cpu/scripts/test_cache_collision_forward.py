import itertools
import unittest

import test_cache_lru_storage as lru_tests


class CacheCollisionForwardTests(lru_tests.CacheLruStorageTests):
    def candidate_path(self):
        return lru_tests.PROJECT / 'experiments/cache_collision_forward/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        if reference_only:
            return miter
        monitor = '''    generate if(READONLY==0) begin : collision_equivalence
        wire original_collision=(exercised.cache.synchronous_writable.store_hit || exercised.cache.synchronous_writable.store_fill) &&
            exercised.cache.synchronous_writable.store_index==exercised.cache.synchronous_writable.read_index;
        always @(posedge exercised.clk) if(exercised.rst_n) begin
            check((exercised.cache.synchronous_writable.hit_forward || exercised.cache.synchronous_writable.fill_forward)===original_collision,
                "factored collision matches original index comparator");
            check({exercised.cache.synchronous_writable.forward_way1,exercised.cache.synchronous_writable.forward_way0}===
                {reference_cache.synchronous_writable.forward_way1,reference_cache.synchronous_writable.forward_way0},
                "registered forwarding flags match independent reference");
            if(exercised.cache.synchronous_writable.store_hit) check(!exercised.cache.synchronous_writable.writeback_read,"store hit is not writeback");
            if(exercised.cache.synchronous_writable.store_fill) check(!exercised.req_ready && !exercised.cache.synchronous_writable.writeback_read,
                "fill has neither new request nor writeback read");
        end
    end endgenerate
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_synchronous_forwarding_writeback_coverage(self):
        for bits, set_bits, fast_read, fast_write, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                result = self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read, fast_write=fast_write,
                                       overlap=overlap, geometry=1, synchronous_coverage=True)
                self.require_pass(result)
                self.assertIn('SYNC_WRITE forward0=', result.stdout)
        print('PASS32 synchronous writable forwarding,byte merge,writeback stall and beat coverage configurations')

    def test_compiled_collision_mutations(self):
        mutations = (
            ('hit_forward=store_hit &&', "hit_forward=1'b0 &&"),
            ('fill_forward=store_fill &&', "fill_forward=1'b0 &&"),
            ('(!req_ready ||', '(req_ready ||'),
            ('{request_set,request_word}==req_address[WORD_BITS+SET_BITS+1:2]', '{request_set,request_word}!=req_address[WORD_BITS+SET_BITS+1:2]'),
            ('forward_way0<=(hit_forward && !hit_line[SET_BITS]) || (fill_forward && !victim[SET_BITS]);', 'forward_way0<=0;'),
            ('forward_way1<=(hit_forward && hit_line[SET_BITS]) || (fill_forward && victim[SET_BITS]);', 'forward_way1<=0;'),
            ('(fill_forward && !victim[SET_BITS])', '(fill_forward && victim[SET_BITS])'),
            ('(fill_forward && victim[SET_BITS])', '(fill_forward && !victim[SET_BITS])'),
            ('forward_data<=store_data;', 'forward_data<=r_data;'),
            ('(current_word & ~byte_mask) | (request_data & byte_mask)', 'request_data'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS ten compiled collision/forward-data mutation controls rejected')


if __name__ == '__main__':
    unittest.main()
