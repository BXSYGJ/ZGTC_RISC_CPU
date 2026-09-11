import itertools
import unittest

import test_cache_valid_both as both_tests


class CacheValidReuseTests(both_tests.CacheValidBothTests):
    def candidate_path(self):
        return both_tests.enable_tests.valid_tests.select_tests.lru_tests.PROJECT / 'experiments/cache_valid_reuse/rv32_cache.sv'

    def simulate(self, *args, **kwargs):
        mutation = kwargs.get('mutation')
        if mutation is not None:
            original = '!valid[way0] ? way0 : !valid[way1] ? way1 : {lru_storage[request_set],request_set}'
            before, after = mutation
            if before == original:
                kwargs['mutation'] = (before.replace('valid[way0]', 'lookup_valid0').replace('valid[way1]', 'lookup_valid1'), after)
        return super().simulate(*args, **kwargs)

    def transform_miter(self, miter, reference_only):
        miter = super().transform_miter(miter, reference_only)
        if reference_only:
            return miter
        monitor = '''    integer replacement_checks=0;
    always @(posedge exercised.clk) if(exercised.rst_n && exercised.cache.state==1) begin
        check(exercised.cache.replacement===reference_cache.replacement,
            "replacement matches original array selection at every lookup");
        replacement_checks=replacement_checks+1;
    end
    final begin
        if(replacement_checks==0) $fatal(1,"FAIL cache missing replacement comparisons");
        $display("VALID_REUSE replacement_checks=%0d",replacement_checks);
    end
'''
        self.assertEqual(miter.count('    task automatic check'), 1)
        return miter.replace('    task automatic check', monitor + '    task automatic check')

    def test_replacement_selection_mutations(self):
        mutations = (
            ('replacement=!lookup_valid0 ?', 'replacement=lookup_valid0 ?'),
            ('way0 : !lookup_valid1 ? way1 :', 'way0 : lookup_valid1 ? way1 :'),
            ('!lookup_valid0 ? way0 :', '!lookup_valid0 ? way1 :'),
            ('!lookup_valid1 ? way1 :', '!lookup_valid1 ? way0 :'),
        )
        for readonly, mutation in itertools.product((0, 1), mutations):
            with self.subTest(readonly=readonly, mutation=mutation):
                result = self.simulate(readonly=readonly, mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Require a compiled replacement-selection rejection')
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS eight readonly/writable replacement selection mutations rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
