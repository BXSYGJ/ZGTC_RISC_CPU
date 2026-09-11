import unittest

import test_cache_data_select as select_tests


class CacheValidPipelineTests(select_tests.CacheDataSelectTests):
    def candidate_path(self):
        return select_tests.lru_tests.PROJECT / 'experiments/cache_valid_pipeline/rv32_cache.sv'

    def transform_miter(self, miter, reference_only):
        miter = super().transform_miter(miter, reference_only)
        self.assertEqual(miter.count('parameter integer CHECK_TAG_PIPELINE=0;'), 1)
        miter = miter.replace('parameter integer CHECK_TAG_PIPELINE=0;', 'parameter integer CHECK_TAG_PIPELINE=1;')
        if reference_only:
            return miter
        monitor = '''    generate if(READONLY==0) begin : valid_pipeline_equivalence
        integer valid_checks=0;
        always @(posedge exercised.clk) if(exercised.rst_n && exercised.cache.state==1) begin
            check({exercised.cache.lookup_valid1,exercised.cache.lookup_valid0}===
                {exercised.cache.valid[exercised.cache.way1],exercised.cache.valid[exercised.cache.way0]},
                "prefetched valid bits equal actual lookup metadata");
            valid_checks=valid_checks+1;
        end
        final begin
            if(valid_checks==0) $fatal(1,"FAIL cache missing valid comparisons");
            $display("VALID_PIPELINE lookup_checks=%0d",valid_checks);
        end
    end endgenerate
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_valid_capture_and_fill_mutations(self):
        mutations = (
            ('valid_set=req_ready ?', "valid_set=1'b0 ?"),
            ('valid_set=req_ready ?', "valid_set=1'b1 ?"),
            ('read_valid0<=(fill_commit &&', "read_valid0<=(1'b0 &&"),
            ('read_valid1<=(fill_commit &&', "read_valid1<=(1'b0 &&"),
            ('|| valid[valid_way0]', '|| valid[valid_way1]'),
            ('|| valid[valid_way1]', '|| valid[valid_way0]'),
            ('                    read_valid0<=', '                    if(req_valid) read_valid0<='),
            ('                    read_valid1<=', '                    if(req_valid) read_valid1<='),
            ('hit0=lookup_valid0 &&', 'hit0=lookup_valid1 &&'),
            ('hit1=lookup_valid1 &&', 'hit1=lookup_valid0 &&'),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Require a compiled functional rejection')
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS ten valid capture/fill/way functional mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
