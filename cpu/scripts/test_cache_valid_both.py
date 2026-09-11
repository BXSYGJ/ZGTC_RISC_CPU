import itertools
import unittest

import test_cache_valid_enable as enable_tests


class CacheValidBothTests(enable_tests.CacheValidEnableTests):
    def candidate_path(self):
        return enable_tests.valid_tests.select_tests.lru_tests.PROJECT / 'experiments/cache_valid_both/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        miter = super().transform_miter(miter, reference_only)
        if reference_only:
            return miter
        for block in ('valid_enable_capture', 'valid_pipeline_equivalence'):
            before = 'generate if(READONLY==0) begin : ' + block
            self.assertEqual(miter.count(before), 1)
            miter = miter.replace(before, 'generate begin : ' + block)
        return miter

    def transform_bench(self, bench):
        bench = super().transform_bench(bench)
        declaration = '    reg inject_read_error=0,inject_write_error=0,inject_early_last=0,inject_late_last=0;'
        error = 'r_error<=active_error && active_beat==1;'
        anchor = '        if(GEOMETRY_STREAM!=0) begin'
        for text in (declaration, error, anchor):
            self.assertEqual(bench.count(text), 1)
        bench = bench.replace(declaration, declaration + '\n    reg error_on_last_beat=0;')
        bench = bench.replace(error, 'r_error<=active_error && (error_on_last_beat ? active_beat==active_final : active_beat==1);')
        prefix = '''        if(READONLY!=0) begin
            flush_cache(0);
            error_on_last_beat=1; inject_read_error=1;
            transact(32'h80,0,0,0,0,1);
            inject_read_error=0; error_on_last_beat=0;
            transact(32'h80,0,0,0,32'h10000020,0);
            flush_cache(0);
            $display("READONLY_LAST_ERROR rejected_and_retried");
        end
'''
        return bench.replace(anchor, prefix + anchor)

    def test_readonly_geometry_forwarding(self):
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (6, 9), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                result = self.simulate(bits=bits, readonly=1, set_bits=set_bits, fast_read=fast_read,
                                       fast_write=0, overlap=overlap, geometry=1, synchronous_coverage=True)
                self.require_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                self.assertIn('VALID_ENABLE capture_checks=', result.stdout)
        print('PASS16 readonly physical geometry, valid capture, fill forwarding and overlap configurations')

    def test_readonly_valid_capture_and_fill_mutations(self):
        mutations = (
            ('else if(req_ready) begin', "else if(1'b0 && req_ready) begin"),
            ('else if(req_ready) begin', "else if(1'b1) begin"),
            ('else if(req_ready) begin', 'else if(req_valid && req_ready) begin'),
            ('else if(req_ready) begin', 'else if(req_ready && state==IDLE) begin'),
            ('else if(fill_commit) begin', "else if(1'b0 && fill_commit) begin"),
            ('if(!victim[SET_BITS]) read_valid0<=1;', 'if(victim[SET_BITS]) read_valid0<=1;'),
            ('read_valid0<=valid[valid_way0];', 'read_valid0<=valid[valid_way1];'),
            ('read_valid1<=valid[valid_way1];', 'read_valid1<=valid[valid_way0];'),
            ('if(!victim[SET_BITS]) read_valid0<=1;', 'if(!victim[SET_BITS]) read_valid0<=0;'),
            ('else read_valid1<=1;', 'else read_valid1<=0;'),
            ('hit0=lookup_valid0 &&', 'hit0=lookup_valid1 &&'),
            ('hit1=lookup_valid1 &&', 'hit1=lookup_valid0 &&'),
            ('last_beat && !r_error && !fill_failed;', 'last_beat && !fill_failed;'),
            ('last_beat && !r_error && !fill_failed;', 'last_beat && !r_error;'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(readonly=1, mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Require a compiled behavioral or capture-contract rejection')
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS fourteen readonly valid capture/fill/error/overlap behavioral or contract mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
