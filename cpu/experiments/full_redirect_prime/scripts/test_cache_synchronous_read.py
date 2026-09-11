import hashlib
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = 'd66a1daf2969e316084221c0ffe86772ad1b8add0540c0989ed215121f3cce8b'


class CacheSynchronousRead(unittest.TestCase):
    def simulate(self, bits=16, readonly=1, fast_read=1, fast_write=1, overlap=1,
                 set_bits=1, geometry=0, variant='positive'):
        source = (PROJECT / 'rtl/rv32_cache.sv').read_text(encoding='utf-8')
        reference = (PROJECT / 'experiments/cache_readonly_writeback/rv32_cache.sv').read_bytes()
        self.assertEqual(hashlib.sha256(reference).hexdigest(), REFERENCE_SHA256)
        if variant == 'reference':
            source = reference.decode()
        reference = reference.decode().replace('module rv32_cache #(', 'module rv32_cache_reference #(')
        mutations = {
            'stale_request_index': ('read_index=req_ready ?', "read_index=1'b0 ?"),
            'live_busy_index': ('read_index=req_ready ?', "read_index=1'b1 ?"),
            'missing_way0_forward': ('forward_way0<=fill_write &&', "forward_way0<=1'b0 &&"),
            'missing_way1_forward': ('forward_way1<=fill_write &&', "forward_way1<=1'b0 &&"),
            'wrong_read_way': ('assign current_word=hit1 ?', 'assign current_word=!hit1 ?'),
            'wrong_fill_way': ('if(fill_write && !victim[SET_BITS]) storage_way0',
                               'if(fill_write && victim[SET_BITS]) storage_way0'),
            'request_only_read': ('read_way0<=storage_way0[read_index];',
                                  'if(req_valid) read_way0<=storage_way0[read_index];'),
        }
        if variant not in ('positive', 'reference'):
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='cache-sync-read-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            baseline = work / 'rv32_cache_reference.sv'
            rtl.write_text(source, encoding='utf-8')
            baseline.write_text(reference, encoding='utf-8')
            image = work / 'test.vvp'
            parameters = dict(ADDRESS_BITS=bits, READONLY=readonly, FAST_READ_HIT=fast_read,
                              FAST_WRITE_HIT=fast_write, READ_OVERLAP=overlap,
                              CACHE_SET_BITS=set_bits, GEOMETRY_STREAM=geometry,
                              CHECK_SYNC_READ=int(geometry != 0 and readonly != 0 and variant != 'reference'))
            command = ['iverilog', '-g2012', '-s', 'cache_ready_payload_tb', '-o', str(image)]
            command += [f'-Pcache_ready_payload_tb.{name}={value}' for name, value in parameters.items()]
            command += [str(rtl), str(baseline), str(PROJECT / 'sim/cache_tb.sv'),
                        str(PROJECT / 'sim/cache_ready_payload_tb.sv')]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], text=True, capture_output=True, timeout=60)

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS cache', result.stdout)
        self.assertIn('READY_PAYLOAD idle=', result.stdout)

    def test_reference_equivalence_all_modes(self):
        for bits, readonly, fast_read, fast_write, overlap in itertools.product((16, 32), (0, 1), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                self.assert_pass(self.simulate(bits, readonly, fast_read, fast_write, overlap))
                print(f'PASS synchronous cache bits={bits} readonly={readonly} fast_read={fast_read} fast_write={fast_write} overlap={overlap}')

    def test_physical_geometries(self):
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (6, 8), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                self.assert_pass(self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read,
                                               overlap=overlap, geometry=1, variant='reference'))
                result = self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap, geometry=1)
                self.assert_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                print(f'PASS synchronous geometry bits={bits} sets={1 << set_bits} fast_read={fast_read} overlap={overlap}')

    def test_compiled_runtime_mutations(self):
        for variant in ('stale_request_index', 'live_busy_index', 'missing_way0_forward',
                        'missing_way1_forward', 'wrong_read_way', 'wrong_fill_way', 'request_only_read'):
            with self.subTest(variant=variant):
                result = self.simulate(set_bits=8, geometry=1, variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Mutation must fail a functional assertion, not only coverage')
                print(f'PASS synchronous cache rejects {variant}')


if __name__ == '__main__':
    unittest.main()
