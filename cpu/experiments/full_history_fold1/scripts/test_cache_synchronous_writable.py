import hashlib
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = '680f03df60a726dab321904a2f72ff2c2a94b9e7d7d5d20842b4492b1cdc57f5'


class CacheSynchronousWritable(unittest.TestCase):
    def simulate(self, bits=16, readonly=1, fast_read=1, fast_write=1, overlap=1,
                 set_bits=1, geometry=0, variant='positive'):
        source = (PROJECT / 'experiments/cache_synchronous_writable/rv32_cache.sv').read_text(encoding='utf-8')
        reference = (PROJECT / 'experiments/cache_tag_pipeline/baseline.sv').read_bytes()
        self.assertEqual(hashlib.sha256(reference).hexdigest(), REFERENCE_SHA256)
        if variant == 'reference':
            source = reference.decode()
        reference = reference.decode().replace('module rv32_cache #(', 'module rv32_cache_reference #(')
        mutations = {
            'stale_request_index': ('read_index=req_ready ?', "read_index=1'b0 ?"),
            'live_busy_index': ('read_index=req_ready ?', "read_index=1'b1 ?"),
            'missing_way0_forward': ('forward_way0<=(store_hit || store_fill) &&', "forward_way0<=1'b0 &&"),
            'missing_way1_forward': ('forward_way1<=(store_hit || store_fill) &&', "forward_way1<=1'b0 &&"),
            'wrong_writeback_way': ('assign w_data=victim[SET_BITS] ?', 'assign w_data=!victim[SET_BITS] ?'),
            'late_writeback_advance': ("? beat+1'b1 : beat", '? beat : beat'),
            'early_writeback_advance': ('state==WB_DATA && w_ready && !last_beat', 'state==WB_DATA && !last_beat'),
            'missing_command_prefetch': ('writeback_read=state==WB_CMD || state==WB_DATA', 'writeback_read=state==WB_DATA'),
            'stale_first_writeback_beat': ("state==WB_CMD ? {WORD_BITS{1'b0}} :", "1'b0 ? {WORD_BITS{1'b0}} :"),
            'wrong_store_way': ('store_way=store_hit ? hit_line[SET_BITS] : victim[SET_BITS]', 'store_way=store_hit ? !hit_line[SET_BITS] : !victim[SET_BITS]'),
            'unmerged_byte_store': ('(current_word & ~byte_mask) | (request_data & byte_mask)', 'request_data'),
            'wrong_forward_payload': ('forward_data<=store_data;', 'forward_data<=r_data;'),
            'request_only_read': ('read_way0<=storage_way0[read_index];', 'if(req_valid) read_way0<=storage_way0[read_index];'),
        }
        if variant not in ('positive', 'reference'):
            old, new = mutations[variant]
            prefix, writable = source.split('        end else begin : synchronous_writable', 1)
            self.assertEqual(writable.count(old), 1)
            source = prefix + '        end else begin : synchronous_writable' + writable.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='cache-sync-writable-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            baseline = work / 'rv32_cache_reference.sv'
            rtl.write_text(source, encoding='utf-8')
            baseline.write_text(reference, encoding='utf-8')
            image = work / 'test.vvp'
            parameters = dict(ADDRESS_BITS=bits, READONLY=readonly, FAST_READ_HIT=fast_read,
                              FAST_WRITE_HIT=fast_write, READ_OVERLAP=overlap,
                              CACHE_SET_BITS=set_bits, GEOMETRY_STREAM=geometry,
                              CHECK_SYNC_WRITE=int(geometry != 0 and readonly == 0 and variant != 'reference'),
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
                print(f'PASS synchronous writable cache bits={bits} readonly={readonly} fast_read={fast_read} fast_write={fast_write} overlap={overlap}')

    def test_physical_geometries(self):
        for bits, set_bits, fast_read, overlap in itertools.product((16, 32), (6, 8), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap):
                self.assert_pass(self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read,
                                               overlap=overlap, geometry=1, variant='reference'))
                result = self.simulate(bits=bits, set_bits=set_bits, fast_read=fast_read, overlap=overlap, geometry=1)
                self.assert_pass(result)
                self.assertIn('SYNC_READ forwarded_way0=', result.stdout)
                print(f'PASS synchronous writable geometry bits={bits} sets={1 << set_bits} fast_read={fast_read} overlap={overlap}')

    def test_writable_physical_geometries(self):
        for bits, set_bits, fast_read, fast_write, overlap in itertools.product((16, 32), (6, 8), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, set_bits=set_bits, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                parameters = dict(bits=bits, readonly=0, set_bits=set_bits, fast_read=fast_read,
                                  fast_write=fast_write, overlap=overlap, geometry=1)
                self.assert_pass(self.simulate(**parameters, variant='reference'))
                result = self.simulate(**parameters)
                self.assert_pass(result)
                self.assertIn('SYNC_WRITE forward0=', result.stdout)
                print(f'PASS writable physical geometry bits={bits} sets={1 << set_bits} fast_read={fast_read} fast_write={fast_write} overlap={overlap}')
    def test_compiled_runtime_mutations(self):
        for variant in ('stale_request_index', 'live_busy_index', 'missing_way0_forward',
                        'missing_way1_forward', 'wrong_writeback_way', 'late_writeback_advance',
                        'early_writeback_advance', 'missing_command_prefetch', 'wrong_store_way',
                        'stale_first_writeback_beat',
                        'unmerged_byte_store', 'wrong_forward_payload', 'request_only_read'):
            with self.subTest(variant=variant):
                result = self.simulate(readonly=0, variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                failures = [line for line in (result.stdout + result.stderr).splitlines()
                            if 'FAIL cache' in line and 'coverage' not in line]
                self.assertTrue(failures, 'Mutation must fail a functional assertion, not only coverage')
                print(f'PASS synchronous writable cache rejects {variant}')


if __name__ == '__main__':
    unittest.main()
