import argparse
import hashlib
import sys
import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CANDIDATE_NAME = 'direct_array'
BASELINE_SHA256 = 'db55cbf5bc327dc78fa55159ca3443e1c2c26b3b3a86a2bc0eec045d838f556e'


class CacheLruStorageTests(unittest.TestCase):
    def candidate_path(self):
        return PROJECT / f'experiments/cache_lru_storage/rv32_cache_{CANDIDATE_NAME}.sv'

    def transform_miter(self, miter, reference_only):
        return miter

    def transform_bench(self, bench):
        return bench

    def simulate(self, bits=16, readonly=0, fast_read=1, fast_write=1, overlap=1,
                 set_bits=1, geometry=0, initial_value=-1, mutation=None, reference_only=False, synchronous_coverage=False):
        original = (PROJECT / 'experiments/cache_synchronous_writable/rv32_cache.sv').read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), BASELINE_SHA256)
        source = self.candidate_path().read_text()
        if reference_only:
            source = original.decode()
        if mutation is not None:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        baseline = original.decode().replace('module rv32_cache #(', 'module rv32_cache_reference #(')
        miter = (PROJECT / 'sim/cache_ready_payload_tb.sv').read_text()
        strict = '''            check({exercised.cache.state,exercised.cache.valid,exercised.cache.dirty,exercised.cache.lru}===
                {reference_cache.state,reference_cache.valid,reference_cache.dirty,reference_cache.lru},
                "reference transaction and cache metadata equivalence");'''
        semantic = '''            check({exercised.cache.state,exercised.cache.valid,exercised.cache.dirty}===
                {reference_cache.state,reference_cache.valid,reference_cache.dirty},
                "reference transaction and valid/dirty equivalence");
            check(((observed_lru ^ reference_cache.lru) & lru_compare_mask)==='0,"trained LRU matches reference");
            if(lru_compare_mask!='0) lru_checks=lru_checks+1;
            if(exercised.cache.state==1 && !(exercised.cache.hit0 || exercised.cache.hit1))
                check(exercised.cache.replacement===reference_cache.replacement,"untrained replacement never depends on unknown LRU");'''
        self.assertEqual(miter.count(strict), 1)
        miter = miter.replace(strict, semantic)
        observed_storage = 'lru' if reference_only else 'lru_storage'
        initialization = ''
        if not reference_only and initial_value >= 0:
            initialization = f'''    initial for(integer initialize_set=0;initialize_set<(1<<CACHE_SET_BITS);initialize_set=initialize_set+1)
        exercised.cache.lru_storage[initialize_set]=1'b{initial_value};
'''
        monitor = '''    reg [(1<<CACHE_SET_BITS)-1:0] lru_trained='0;
    wire [(1<<CACHE_SET_BITS)-1:0] observed_lru;
    wire [(1<<CACHE_SET_BITS)-1:0] lru_compare_mask=lru_trained |
        (reference_cache.valid[(1<<CACHE_SET_BITS)-1:0] & reference_cache.valid[(2<<CACHE_SET_BITS)-1:(1<<CACHE_SET_BITS)]);
    for(genvar observed_set=0;observed_set<(1<<CACHE_SET_BITS);observed_set=observed_set+1) begin : observe_storage
        assign observed_lru[observed_set]=exercised.cache.OBSERVED_STORAGE[observed_set];
    end
    integer lru_checks=0;
    always @(posedge exercised.clk or negedge exercised.rst_n) begin
        if(!exercised.rst_n) lru_trained<='0;
        else if(reference_cache.state==1 && (reference_cache.hit0 || reference_cache.hit1))
            lru_trained[reference_cache.request_set]<=1;
    end
    final begin
        if(lru_checks==0) $fatal(1,"FAIL cache no trained LRU comparisons");
        $display("LRU_STORAGE compared=%0d",lru_checks);
    end
'''
        monitor = monitor.replace('OBSERVED_STORAGE', observed_storage)
        miter = miter.replace('    task automatic check', initialization + monitor + '    task automatic check')
        miter = self.transform_miter(miter, reference_only)
        bench = self.transform_bench((PROJECT / 'sim/cache_tb.sv').read_text())
        reset_prefix = '''        for(integer reset_round=0;reset_round<3;reset_round=reset_round+1) begin
            transact(0,0,0,0,memory[0],0);
            transact(32'd1<<(CACHE_SET_BITS+4),0,0,0,memory[1<<(CACHE_SET_BITS+2)],0);
            transact(0,0,0,0,memory[0],0);
            @(negedge clk); req_valid=0; rsp_ready=0; flush_valid=0; rst_n=0;
            repeat(3) @(negedge clk); rst_n=1;
        end
'''
        reset_anchor = '        if(GEOMETRY_STREAM!=0) begin'
        self.assertEqual(bench.count(reset_anchor), 1)
        capacity_overlap = '''        if(GEOMETRY_STREAM==2 && READ_OVERLAP!=0) begin
            transact(0,0,0,0,32'h10000000,0);
            snapshot_commands=command_count;
            if(FAST_READ_HIT!=0) overlap_stream();
            else slow_overlap_stream();
        end
'''
        bench = bench.replace(reset_anchor, reset_prefix + capacity_overlap + reset_anchor)
        with tempfile.TemporaryDirectory(prefix='cache-lru-storage-') as directory:
            work = Path(directory)
            files = {'candidate.sv': source, 'reference.sv': baseline, 'miter.sv': miter, 'bench.sv': bench}
            for name, text in files.items():
                (work / name).write_text(text, encoding='utf-8')
            parameters = dict(ADDRESS_BITS=bits, READONLY=readonly, FAST_READ_HIT=fast_read,
                              FAST_WRITE_HIT=fast_write, READ_OVERLAP=overlap,
                              CACHE_SET_BITS=set_bits, GEOMETRY_STREAM=geometry,
                              CHECK_SYNC_WRITE=int(synchronous_coverage and readonly == 0),
                              CHECK_SYNC_READ=int(synchronous_coverage and readonly != 0))
            output = work / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'cache_ready_payload_tb', '-o', str(output)]
            command += [f'-Pcache_ready_payload_tb.{name}={value}' for name, value in parameters.items()]
            command += [str(work / name) for name in files]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=120)

    def require_pass(self, result, capacity=False):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS instruction capacity' if capacity else 'PASS cache', result.stdout)
        self.assertIn('READY_PAYLOAD idle=', result.stdout)
        self.assertIn('LRU_STORAGE compared=', result.stdout)

    def test_all_modes_and_arbitrary_power_up_state(self):
        for bits, readonly, fast_read, fast_write, overlap, initial_value in itertools.product(
                (16, 32), (0, 1), (0, 1), (0, 1), (0, 1), (-1, 0, 1)):
            with self.subTest(bits=bits, readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap, initial_value=initial_value):
                self.require_pass(self.simulate(bits, readonly, fast_read, fast_write, overlap, initial_value=initial_value))
        print('PASS 96 mode/power-up configurations including three trained resets each')

    def test_physical_geometries_and_independent_reference(self):
        for bits, readonly, set_bits, fast_read, overlap in itertools.product((16, 32), (0, 1), (6, 9), (0, 1), (0, 1)):
            with self.subTest(bits=bits, readonly=readonly, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                parameters = dict(bits=bits, readonly=readonly, set_bits=set_bits, fast_read=fast_read, overlap=overlap, geometry=1)
                self.require_pass(self.simulate(**parameters))
                self.require_pass(self.simulate(**parameters, reference_only=True))
        print('PASS 32 physical configurations and 32 independent reference controls')

    def test_full_readonly_capacity(self):
        for set_bits, initial_value, reference_only in itertools.product((9, 10), (-1, 0, 1), (False, True)):
            with self.subTest(set_bits=set_bits, initial_value=initial_value, reference_only=reference_only):
                self.require_pass(self.simulate(readonly=1, set_bits=set_bits, geometry=2, initial_value=initial_value,
                                                reference_only=reference_only), capacity=True)
        print('PASS six whole-capacity arbitrary-LRU tests and six independent reference controls')

    def test_invalid_aliases_preserve_even_untrained_storage(self):
        candidate = self.candidate_path().read_text()
        reference = (PROJECT / 'experiments/cache_synchronous_writable/rv32_cache.sv').read_text()
        bench = (PROJECT / 'sim/cache_bounds_tb.sv').read_text()
        before = 'cache.lru==saved_lru'
        self.assertEqual(bench.count(before), 1)
        bench = bench.replace(before, 'cache.lru===saved_lru')
        for geometry, readonly, overlap, source in itertools.product(((13, 1), (16, 6), (16, 9)), (0, 1), (0, 1), (candidate, reference)):
            bits, set_bits = geometry
            with self.subTest(bits=bits, set_bits=set_bits, readonly=readonly, overlap=overlap, reference=source is reference):
                with tempfile.TemporaryDirectory(prefix='lru-bounds-') as directory:
                    work = Path(directory)
                    rtl = work / 'cache.sv'
                    testbench = work / 'bounds.sv'
                    rtl.write_text(source, encoding='utf-8')
                    active_bench = bench
                    if source is candidate and CANDIDATE_NAME != 'async_guard':
                        observation = "    wire [(1<<SET_BITS)-1:0] observed_lru;\n    for(genvar observed_set=0;observed_set<(1<<SET_BITS);observed_set=observed_set+1) begin : observe_lru\n        assign observed_lru[observed_set]=cache.lru_storage[observed_set];\n    end\n"
                        active_bench = active_bench.replace('    initial begin', observation + '    initial begin', 1).replace('cache.lru', 'observed_lru')
                        active_bench = active_bench.replace('observed_lru_storage[observed_set]', 'cache.lru_storage[observed_set]')
                    testbench.write_text(active_bench, encoding='utf-8')
                    image = work / 'bounds.vvp'
                    command = ['iverilog', '-g2012', '-s', 'cache_bounds_tb', '-o', str(image),
                               f'-Pcache_bounds_tb.ADDRESS_BITS={bits}', f'-Pcache_bounds_tb.SET_BITS={set_bits}',
                               f'-Pcache_bounds_tb.READ_ONLY={readonly}', f'-Pcache_bounds_tb.READ_OVERLAP={overlap}',
                               str(rtl), str(PROJECT / 'rtl/rv32_burst_ram.sv'), str(testbench)]
                    compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                    result = subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS cache_bounds', result.stdout)
        print('PASS 12 candidate and 12 reference address/alias boundary configurations')

    def test_compiled_functional_mutations_rejected(self):
        mutations = (
            ('lru_storage[request_set]<=!hit_line[SET_BITS]', 'lru_storage[request_set]<=hit_line[SET_BITS]'),
            ('else if(state==LOOKUP && (hit0 || hit1)) lru_storage', "else if(1'b0 && state==LOOKUP && (hit0 || hit1)) lru_storage"),
            ('lru_storage[request_set]<=', "lru_storage[request_set ^ {{(SET_BITS-1){1'b0}},1'b1}]<="),
            ("!valid[way0] ? way0 : !valid[way1] ? way1 : {lru[request_set],request_set}", '{lru_storage[request_set],request_set}'),
            ('else if(state==LOOKUP && (hit0 || hit1)) lru_storage', 'else if(state==IDLE) lru_storage'),
        )
        if CANDIDATE_NAME != 'async_guard':
            mutations = tuple((before.replace('{lru[request_set],request_set}', '{lru_storage[request_set],request_set}'), after) for before, after in mutations)
        for readonly, mutation in itertools.product((0, 1), mutations):
            if CANDIDATE_NAME == 'readonly_generated' and readonly == 0:
                before, after = mutation
                before = before.replace('lru_storage[request_set]<=', 'lru_storage[lru_set]<=')
                after = after.replace('lru_storage[request_set]<=', 'lru_storage[lru_set]<=').replace('lru_storage[request_set ^', 'lru_storage[lru_set ^')
                before = before.replace('(hit0 || hit1)) lru_storage', "(hit0 || hit1) && request_set==lru_set[SET_BITS-1:0]) lru_storage")
                after = after.replace('(hit0 || hit1)) lru_storage', "(hit0 || hit1) && request_set==lru_set[SET_BITS-1:0]) lru_storage")
                if before == 'lru_storage[lru_set]<=':
                    update_guard = 'else if(state==LOOKUP && (hit0 || hit1) && request_set==lru_set[SET_BITS-1:0]) '
                    before, after = update_guard + before, update_guard + after
                mutation = before, after
            with self.subTest(readonly=readonly, mutation=mutation):
                result = self.simulate(readonly=readonly, mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                self.assertNotIn('watchdog', (result.stdout + result.stderr).lower())
        print('PASS ten compiled LRU semantic failures rejected')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--candidate', choices=('async_guard', 'direct_array', 'readonly_ram', 'readonly_generated'), default='direct_array')
    args, remaining = parser.parse_known_args()
    CANDIDATE_NAME = args.candidate
    unittest.main(argv=[sys.argv[0], *remaining])
