import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/early-direct-carry8-146250-stage/rtl/rv32_cache.sv'
CANDIDATE = ROOT / 'experiments/dcache_valid_banks/rv32_cache.sv'


class ValidBanksTests(unittest.TestCase):
    def simulate(self, source, top, parameters):
        with tempfile.TemporaryDirectory(prefix='dcache-valid-banks-') as temporary:
            directory = Path(temporary)
            candidate = directory / 'rv32_cache.sv'
            reference = directory / 'rv32_cache_reference.sv'
            candidate.write_text(source, encoding='utf-8')
            reference.write_text(PARENT.read_text().replace('module rv32_cache #(', 'module rv32_cache_reference #(', 1), encoding='utf-8')
            output = directory / 'test.vvp'
            files = [candidate, reference, ROOT / 'sim' / (top + '.sv')]
            if top == 'cache_valid_banks_pairs_tb':
                files.append(ROOT / 'sim/cache_tb.sv')
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output)]
            command += [f'-P{top}.{name}={value}' for name, value in parameters.items()]
            command += list(map(str, files))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=180)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=60)

    def test_exact_source_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), 'EE88049C2B8FB3F8BD94A8C42B184CBE3181269DC40DCDA49DFD8784E4C653B1')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), 'A3B10973E0D24038B46FC8D387F400E6256B54CDD3027F21035B1EBCABFA9B9B')
        original = PARENT.read_text()
        candidate = CANDIDATE.read_text()
        start = '    generate\n        begin : synchronous_valid'
        end = '    generate\n        if(READ_ONLY!=0)'
        start_new = '    generate\n        if(READ_ONLY==0 && SET_BITS>4)'
        self.assertEqual(original[:original.index(start)], candidate[:candidate.index(start_new)])
        self.assertEqual(original[original.index(end):], candidate[candidate.index(end):])
        unchanged = original[original.index('            wire [SET_BITS-1:0] valid_set'):original.index(end)]
        self.assertTrue(candidate[:candidate.index(end)].endswith(unchanged))

    def test_direct_equivalence(self):
        for sets, readonly in ((1, 0), (4, 0), (5, 0), (6, 0), (7, 0), (6, 1), (9, 1)):
            with self.subTest(sets=sets, readonly=readonly):
                result = self.simulate(CANDIDATE.read_text(), 'cache_valid_banks_tb', dict(SET_BITS=sets, READ_ONLY=readonly))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS valid_banks checks=', result.stdout)
                print(result.stdout.strip())

    def test_real_cache_pairs(self):
        matrix = []
        for read in (0, 1):
            for write in (0, 1):
                for overlap in (0, 1):
                    matrix.append(dict(ADDRESS_BITS=16, CACHE_SET_BITS=6, READONLY=0, FAST_READ_HIT=read, FAST_WRITE_HIT=write, READ_OVERLAP=overlap, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=1))
        for sets in (1, 4, 5, 7, 8):
            matrix.append(dict(ADDRESS_BITS=16, CACHE_SET_BITS=sets, READONLY=0, FAST_READ_HIT=1, FAST_WRITE_HIT=1, READ_OVERLAP=1, CHECK_SYNC_WRITE=1, GEOMETRY_STREAM=1))
        matrix.append(dict(ADDRESS_BITS=16, CACHE_SET_BITS=9, READONLY=1, FAST_READ_HIT=1, FAST_WRITE_HIT=0, READ_OVERLAP=1, CHECK_SYNC_READ=1, GEOMETRY_STREAM=1))
        for parameters in matrix:
            with self.subTest(parameters=parameters):
                outputs = []
                for path in (PARENT, CANDIDATE):
                    result = self.simulate(path.read_text(), 'cache_valid_banks_pairs_tb', parameters)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('PASS cache', result.stdout)
                    self.assertIn('READY_PAYLOAD', result.stdout)
                    outputs.append(result.stdout)
                self.assertEqual(outputs[0], outputs[1])
                print('PASS valid_banks real cache pair ' + str(parameters))

    def test_runtime_mutants(self):
        source = CANDIDATE.read_text()
        mutations = (
            ('wrong_way', 'wire [15:0] bank_valid1=valid[SETS+bank_index*16+:16];', 'wire [15:0] bank_valid1=valid[bank_index*16+:16];'),
            ('wrong_offset', 'valid0<=bank_valid0[valid_offset];', "valid0<=bank_valid0[valid_offset ^ 4'd1];"),
            ('wrong_bank', 'read_bank<=valid_bank;', 'read_bank<=~valid_bank;'),
            ('live_bank_select', 'lookup_valid0=read_valid0[read_bank];', 'lookup_valid0=read_valid0[valid_bank];'),
            ('missing_fill', 'if(!victim[SET_BITS]) valid0<=1;', 'if(!victim[SET_BITS]) valid0<=0;'),
            ('wrong_fill_way', 'if(!victim[SET_BITS]) valid0<=1;', 'if(victim[SET_BITS]) valid0<=1;'),
            ('error_commits', 'wire fill_commit=state==FILL_DATA && r_valid && r_last && last_beat && !r_error && !fill_failed;', 'wire fill_commit=state==FILL_DATA && r_valid && r_last && last_beat && !fill_failed;'),
        )
        for name, before, after in mutations:
            with self.subTest(name=name):
                self.assertGreaterEqual(source.count(before), 1)
                result = self.simulate(source.replace(before, after, 1), 'cache_valid_banks_tb', dict(SET_BITS=6, READ_ONLY=0))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL valid_banks candidate check=', result.stdout + result.stderr)
                print('PASS valid_banks runtime mutant rejected: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
