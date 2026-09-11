import hashlib
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = '680f03df60a726dab321904a2f72ff2c2a94b9e7d7d5d20842b4492b1cdc57f5'


class CacheTagPipeline(unittest.TestCase):
    def simulate(self, bits=16, readonly=1, fast_read=1, fast_write=1, overlap=1,
                 set_bits=1, geometry=0, variant='positive'):
        source = (PROJECT / 'experiments/cache_tag_pipeline/rv32_cache.sv').read_text(encoding='utf-8')
        reference = (PROJECT / 'experiments/cache_tag_pipeline/baseline.sv').read_bytes()
        self.assertEqual(hashlib.sha256(reference).hexdigest(), REFERENCE_SHA256)
        if variant == 'reference':
            source = reference.decode()
        reference = reference.decode().replace('module rv32_cache #(', 'module rv32_cache_reference #(')
        mutations = {
            'stale_tag_index': ('tag_set=req_ready ?', "tag_set=1'b0 ?"),
            'live_busy_tag_index': ('tag_set=req_ready ?', "tag_set=1'b1 ?"),
            'missing_way0_tag_forward': ('tag_way0<=fill_commit &&', "tag_way0<=1'b0 &&"),
            'missing_way1_tag_forward': ('tag_way1<=fill_commit &&', "tag_way1<=1'b0 &&"),
            'missing_way0_valid_forward': ('valid_way0<=(fill_commit &&', "valid_way0<=(1'b0 &&"),
            'missing_way1_valid_forward': ('valid_way1<=(fill_commit &&', "valid_way1<=(1'b0 &&"),
            'wrong_read_way': ("tags[{1'b0,tag_set}]", "tags[{1'b1,tag_set}]"),
            'request_only_read': ('tag_way0<=fill_commit &&', 'if(req_valid) tag_way0<=fill_commit &&'),
        }
        if variant not in ('positive', 'reference'):
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='cache-tag-pipeline-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            baseline = work / 'rv32_cache_reference.sv'
            rtl.write_text(source, encoding='utf-8')
            baseline.write_text(reference, encoding='utf-8')
            image = work / 'test.vvp'
            parameters = dict(ADDRESS_BITS=bits, READONLY=readonly, FAST_READ_HIT=fast_read,
                              FAST_WRITE_HIT=fast_write, READ_OVERLAP=overlap,
                              CACHE_SET_BITS=set_bits, GEOMETRY_STREAM=geometry,
                              CHECK_TAG_PIPELINE=1,
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
                print(f'PASS tag-pipeline cache bits={bits} readonly={readonly} fast_read={fast_read} fast_write={fast_write} overlap={overlap}')

    def test_physical_geometries(self):
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (6, 8), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                self.assert_pass(self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read,
                                               overlap=overlap, geometry=1, variant='reference'))
                result = self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap, geometry=1)
                self.assert_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                print(f'PASS tag-pipeline geometry bits={bits} sets={1 << set_bits} fast_read={fast_read} overlap={overlap}')

    def test_compiled_runtime_mutations(self):
        for readonly, variant in itertools.product((0, 1), (
                'stale_tag_index', 'live_busy_tag_index', 'missing_way0_tag_forward',
                'missing_way1_tag_forward', 'missing_way0_valid_forward',
                'missing_way1_valid_forward', 'wrong_read_way', 'request_only_read')):
            with self.subTest(readonly=readonly, variant=variant):
                result = self.simulate(readonly=readonly, set_bits=8 if readonly else 1,
                                       geometry=readonly, variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Mutation must fail a functional assertion, not only coverage')
                print(f'PASS tag-pipeline cache readonly={readonly} rejects {variant}')


if __name__ == '__main__':
    unittest.main()
