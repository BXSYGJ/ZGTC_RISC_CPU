import unittest

import test_cache_valid_pipeline as valid_tests


class CacheValidEnableTests(valid_tests.CacheValidPipelineTests):
    def candidate_path(self):
        return valid_tests.select_tests.lru_tests.PROJECT / 'experiments/cache_valid_enable/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        miter = super().transform_miter(miter, reference_only)
        if reference_only:
            return miter
        monitor = '''    generate if(READONLY==0) begin : valid_enable_capture
        reg expected_valid0=0,expected_valid1=0;
        integer capture_checks=0;
        always @(posedge exercised.clk or negedge exercised.rst_n) begin
            if(!exercised.rst_n) begin expected_valid0<=0; expected_valid1<=0; end
            else if(exercised.req_ready) begin
                expected_valid0<=reference_cache.valid[{1'b0,exercised.req_address[CACHE_SET_BITS+3:4]}];
                expected_valid1<=reference_cache.valid[{1'b1,exercised.req_address[CACHE_SET_BITS+3:4]}];
            end else if(reference_cache.state==6 && exercised.r_valid && exercised.r_last &&
                (&reference_cache.beat) && !exercised.r_error && !reference_cache.fill_failed) begin
                if(reference_cache.victim[CACHE_SET_BITS]) expected_valid1<=1;
                else expected_valid0<=1;
                check(reference_cache.victim[CACHE_SET_BITS-1:0]===reference_cache.request_set,
                    "fill victim set belongs to current request");
            end
        end
        always @(negedge exercised.clk) if(exercised.rst_n) begin
            check({exercised.cache.lookup_valid1,exercised.cache.lookup_valid0}==={expected_valid1,expected_valid0},
                "valid enable capture, hold and fill contract");
            capture_checks=capture_checks+1;
        end
        final begin
            if(capture_checks==0) $fatal(1,"FAIL cache missing enabled capture checks");
            $display("VALID_ENABLE capture_checks=%0d",capture_checks);
        end
    end endgenerate
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_valid_capture_and_fill_mutations(self):
        mutations = (
            ('else if(req_ready) begin', "else if(1'b0 && req_ready) begin"),
            ('else if(req_ready) begin', "else if(1'b1) begin"),
            ('else if(req_ready) begin', 'else if(req_valid && req_ready) begin'),
            ('else if(fill_commit) begin', "else if(1'b0 && fill_commit) begin"),
            ('if(!victim[SET_BITS]) read_valid0<=1;', 'if(victim[SET_BITS]) read_valid0<=1;'),
            ('read_valid0<=valid[valid_way0];', 'read_valid0<=valid[valid_way1];'),
            ('read_valid1<=valid[valid_way1];', 'read_valid1<=valid[valid_way0];'),
            ('if(!victim[SET_BITS]) read_valid0<=1;', 'if(!victim[SET_BITS]) read_valid0<=0;'),
            ('else read_valid1<=1;', 'else read_valid1<=0;'),
            ('hit0=lookup_valid0 &&', 'hit0=lookup_valid1 &&'),
            ('hit1=lookup_valid1 &&', 'hit1=lookup_valid0 &&'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Require a compiled behavioral or capture-contract rejection')
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS eleven valid enable/capture/fill behavioral or contract mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
