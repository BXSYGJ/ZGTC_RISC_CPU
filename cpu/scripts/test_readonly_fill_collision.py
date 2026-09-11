import itertools
import unittest

import test_cache_lru_storage as lru_tests


class ReadonlyFillCollisionTests(lru_tests.CacheLruStorageTests):
    def candidate_path(self):
        return lru_tests.PROJECT / 'experiments/readonly_fill_collision/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        if reference_only:
            return miter
        monitor = '''    generate if(READONLY!=0) begin : readonly_collision_equivalence
        wire original_collision=exercised.cache.synchronous_readonly.fill_write &&
            exercised.cache.synchronous_readonly.fill_index==exercised.cache.synchronous_readonly.read_index;
        wire isolated_collision=exercised.cache.synchronous_readonly.fill_write &&
            exercised.cache.synchronous_readonly.fill_index=={exercised.cache.request_set,exercised.cache.request_word};
        integer active_fills=0;
        always @(posedge exercised.clk) if(exercised.rst_n) begin
            check(original_collision===isolated_collision,"readonly original and isolated collision agree");
            check({exercised.cache.synchronous_readonly.forward_way1,exercised.cache.synchronous_readonly.forward_way0}===
                {reference_cache.synchronous_readonly.forward_way1,reference_cache.synchronous_readonly.forward_way0},
                "readonly registered forwarding matches independent reference");
            if(exercised.cache.synchronous_readonly.fill_write) begin
                active_fills=active_fills+1;
                check(!exercised.req_ready,"readonly fill cannot accept another request");
                check(!exercised.cache.rsp_valid,"readonly fill cannot respond concurrently");
            end
        end
        final begin
            if(active_fills==0) $fatal(1,"FAIL cache no active readonly fills");
            $display("READONLY_COLLISION fills=%0d",active_fills);
        end
    end endgenerate
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_exact_scoped_source_change(self):
        baseline = (lru_tests.PROJECT / 'build/load-use-address-plain-stage/rtl/rv32_cache.sv').read_text()
        self.assertEqual(baseline.count('fill_index==read_index'), 2)
        self.assertEqual(self.candidate_path().read_text(), baseline.replace(
            'fill_index==read_index', 'fill_index=={request_set,request_word}'))

    def test_both_readonly_forwarding_ways(self):
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                result = self.simulate(bits=bits, readonly=1, set_bits=set_bits, fast_read=fast_read,
                                       overlap=overlap, geometry=1, synchronous_coverage=True)
                self.require_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                self.assertIn('READONLY_COLLISION fills=', result.stdout)
        print('PASS16 readonly dual-way fill-forwarding configurations')

    def test_compiled_readonly_mutations_rejected(self):
        mutations = (
            ('forward_way0<=fill_write && !victim[SET_BITS]', "forward_way0<=1'b0 && !victim[SET_BITS]"),
            ('forward_way1<=fill_write && victim[SET_BITS]', "forward_way1<=1'b0 && victim[SET_BITS]"),
            ('forward_way0<=fill_write && !victim[SET_BITS]', 'forward_way0<=fill_write && victim[SET_BITS]'),
            ('forward_way1<=fill_write && victim[SET_BITS]', 'forward_way1<=fill_write && !victim[SET_BITS]'),
            ('forward_way0<=fill_write && !victim[SET_BITS] && fill_index=={request_set,request_word}',
             'forward_way0<=fill_write && !victim[SET_BITS] && fill_index!={request_set,request_word}'),
            ('forward_way1<=fill_write && victim[SET_BITS] && fill_index=={request_set,request_word}',
             'forward_way1<=fill_write && victim[SET_BITS] && fill_index!={request_set,request_word}'),
            ('forward_way0<=fill_write && !victim[SET_BITS] && fill_index=={request_set,request_word}',
             'forward_way0<=fill_write && !victim[SET_BITS] && fill_index==req_address[WORD_BITS+SET_BITS+1:2]'),
            ('forward_way1<=fill_write && victim[SET_BITS] && fill_index=={request_set,request_word}',
             'forward_way1<=fill_write && victim[SET_BITS] && fill_index==req_address[WORD_BITS+SET_BITS+1:2]'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(readonly=1, mutation=mutation, synchronous_coverage=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS eight compiled readonly forwarding mutations rejected')


if __name__ == '__main__':
    unittest.main()
