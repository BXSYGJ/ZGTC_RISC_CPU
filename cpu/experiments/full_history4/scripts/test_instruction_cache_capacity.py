import hashlib
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_cache_synchronous_writable as writable_tests


PROJECT = Path(__file__).resolve().parents[1]


class InstructionCapacityTests(unittest.TestCase):
    def test_differential_expanded_geometries(self):
        helper = writable_tests.CacheSynchronousWritable()
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (9, 10), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                parameters = dict(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap, geometry=1)
                helper.assert_pass(helper.simulate(**parameters, variant='reference'))
                result = helper.simulate(**parameters)
                helper.assert_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                print(f'PASS expanded differential sets={1<<set_bits} bits={bits} fast_read={fast_read} overlap={overlap}')

    def sweep(self, set_bits, variant):
        if variant == 'reference':
            path = PROJECT / 'experiments/cache_tag_pipeline/baseline.sv'
            expected = '680f03df60a726dab321904a2f72ff2c2a94b9e7d7d5d20842b4492b1cdc57f5'
        else:
            path = PROJECT / 'experiments/cache_synchronous_writable/rv32_cache.sv'
            expected = 'db55cbf5bc327dc78fa55159ca3443e1c2c26b3b3a86a2bc0eec045d838f556e'
        data = path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
        source = data.decode()
        bench = (PROJECT / 'sim/cache_tb.sv').read_text()
        if variant == 'half_capacity':
            before = '.SET_BITS(CACHE_SET_BITS)'
            self.assertEqual(bench.count(before), 1)
            bench = bench.replace(before, '.SET_BITS(CACHE_SET_BITS-1)')
        with tempfile.TemporaryDirectory(prefix='instruction-capacity-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            driver = work / 'cache_tb.sv'
            rtl.write_text(source, encoding='utf-8')
            driver.write_text(bench, encoding='utf-8')
            image = work / 'capacity.vvp'
            command = ['iverilog', '-g2012', '-s', 'cache_tb', '-o', str(image),
                       '-Pcache_tb.ADDRESS_BITS=16', '-Pcache_tb.READONLY=1',
                       '-Pcache_tb.FAST_READ_HIT=1', '-Pcache_tb.READ_OVERLAP=1',
                       f'-Pcache_tb.CACHE_SET_BITS={set_bits}', '-Pcache_tb.GEOMETRY_STREAM=2',
                       str(rtl), str(driver)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=120)

    def test_all_sets_two_ways_resident_and_replacement(self):
        for set_bits, variant in itertools.product((9, 10), ('positive', 'reference')):
            with self.subTest(set_bits=set_bits, variant=variant):
                result = self.sweep(set_bits, variant)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn(f'PASS instruction capacity sets={1<<set_bits}', result.stdout)
                print(f'PASS whole capacity sets={1<<set_bits} variant={variant}')

    def test_reject_half_capacity_even_with_correct_read_data(self):
        for set_bits in (9, 10):
            with self.subTest(set_bits=set_bits):
                result = self.sweep(set_bits, 'half_capacity')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache full advertised capacity remains resident', result.stdout+result.stderr)
                print(f'PASS rejects half-capacity implementation for sets={1<<set_bits}')


if __name__ == '__main__':
    unittest.main()
