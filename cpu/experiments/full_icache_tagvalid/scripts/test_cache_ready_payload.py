import hashlib
import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = 'ac24edfb561b454437519b452e5f6f90aa4c7dc538400d919919bc011877d633'
READY_BASELINE_SHA256 = 'c3bf25d04a223b502eff329d2dd95bfdd7f4f559506a5df878f38d29dddec8f4'
WRITEBACK_ORIGINAL = '    assign w_data=storage[{victim,beat}];'
WRITEBACK_READONLY = "    assign w_data=READ_ONLY!=0 ? 32'b0 : storage[{victim,beat}];"
PAYLOAD = """            if(req_ready) begin
                request_address<={{(32-ADDRESS_BITS){1'b0}},req_address[ADDRESS_BITS-1:0]}; request_data<=req_data;
                request_strobe<=req_strobe; request_write<=req_write;
            end
            if(req_valid && req_ready) begin"""
ACCEPTED = """            if(req_valid && req_ready) begin
                request_address<={{(32-ADDRESS_BITS){1'b0}},req_address[ADDRESS_BITS-1:0]}; request_data<=req_data;
                request_strobe<=req_strobe; request_write<=req_write;"""


class CacheReadyPayload(unittest.TestCase):
    def simulate(self, bits=16, readonly=0, fast_read=1, fast_write=1, overlap=1, variant='positive'):
        source = (PROJECT / 'experiments/cache_readonly_writeback/rv32_cache.sv').read_text(encoding='utf-8')
        self.assertEqual(source.count(PAYLOAD), 1)
        self.assertEqual(source.count(WRITEBACK_READONLY), 1)
        reference = source.replace(PAYLOAD, ACCEPTED).replace(WRITEBACK_READONLY, WRITEBACK_ORIGINAL)
        self.assertEqual(hashlib.sha256(reference.encode()).hexdigest(), REFERENCE_SHA256)
        reference = reference.replace('module rv32_cache #(', 'module rv32_cache_reference #(')
        mutations = {
            'accepted_only': ('if(req_ready) begin', 'if(req_valid && req_ready) begin'),
            'ignore_busy': ('if(req_ready) begin', 'if(1) begin'),
            'ignore_flush': ('if(req_ready) begin', 'if(req_ready || flush_valid) begin'),
            'idle_only': ('if(req_ready) begin', 'if(state==IDLE && !flush_valid) begin'),
            'invent_transaction': ('if(req_valid && req_ready) begin', 'if(req_ready) begin'),
            'stale_data': ('request_data<=req_data;', 'request_data<=request_data;'),
            'stale_strobe': ('request_strobe<=req_strobe;', 'request_strobe<=request_strobe;'),
            'stale_write': ('request_write<=req_write;', 'request_write<=request_write;'),
            'drop_alignment': ('req_address[ADDRESS_BITS-1:0]}; request_data',
                               "req_address[ADDRESS_BITS-1:2],2'b0}; request_data"),
            'restore_readonly_payload': (WRITEBACK_READONLY, WRITEBACK_ORIGINAL),
            'zero_writable_payload': (WRITEBACK_READONLY, "    assign w_data=32'b0;"),
            'readonly_command': ('assign cmd_write=state==WB_CMD;',
                                 "assign cmd_write=READ_ONLY!=0 ? 1'b1 : state==WB_CMD;"),
            'readonly_dirty': ('valid[victim]<=0; dirty[victim]<=0; fill_failed<=0;',
                               'valid[victim]<=0; dirty[victim]<=1; fill_failed<=0;'),
        }
        if variant != 'positive':
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='cache-ready-payload-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            baseline = work / 'rv32_cache_reference.sv'
            rtl.write_text(source, encoding='utf-8')
            baseline.write_text(reference, encoding='utf-8')
            image = work / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'cache_ready_payload_tb', '-o', str(image),
                       f'-Pcache_ready_payload_tb.ADDRESS_BITS={bits}', f'-Pcache_ready_payload_tb.READONLY={readonly}',
                       f'-Pcache_ready_payload_tb.FAST_READ_HIT={fast_read}',
                       f'-Pcache_ready_payload_tb.FAST_WRITE_HIT={fast_write}',
                       f'-Pcache_ready_payload_tb.READ_OVERLAP={overlap}', str(rtl), str(baseline),
                       str(PROJECT / 'sim/cache_tb.sv'), str(PROJECT / 'sim/cache_ready_payload_tb.sv')]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], text=True, capture_output=True, timeout=30)

    def test_reference_equivalence_all_modes(self):
        for bits, readonly, fast_read, fast_write, overlap in itertools.product((16, 32), (0, 1), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                result = self.simulate(bits, readonly, fast_read, fast_write, overlap)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS cache', result.stdout)
                self.assertIn('READY_PAYLOAD idle=', result.stdout)
                if readonly:
                    self.assertIn('READONLY_WRITEBACK invariant_cycles=', result.stdout)
                print(f'PASS ready payload bits={bits} readonly={readonly} fast_read={fast_read} fast_write={fast_write} overlap={overlap}')

    def test_payload_and_transaction_mutations(self):
        for variant in ('accepted_only', 'ignore_busy', 'ignore_flush', 'idle_only', 'invent_transaction',
                        'stale_data', 'stale_strobe', 'stale_write', 'drop_alignment'):
            with self.subTest(variant=variant):
                result = self.simulate(variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                print(f'PASS ready payload rejects {variant}')


    def test_readonly_writeback_mutations(self):
        for variant, readonly in (('restore_readonly_payload', 1), ('zero_writable_payload', 0),
                                  ('readonly_command', 1), ('readonly_dirty', 1)):
            with self.subTest(variant=variant, readonly=readonly):
                result = self.simulate(readonly=readonly, variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)
                print(f'PASS readonly writeback rejects {variant}')

    def test_qualified_ready_baseline_preserved(self):
        baseline = (PROJECT / 'experiments/cache_ready_payload/rv32_cache.sv').read_bytes()
        source = (PROJECT / 'experiments/cache_readonly_writeback/rv32_cache.sv').read_text(encoding='utf-8')
        self.assertEqual(source.count(WRITEBACK_READONLY), 1)
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), READY_BASELINE_SHA256)
        self.assertEqual(source.replace(WRITEBACK_READONLY, WRITEBACK_ORIGINAL).encode(), baseline)


if __name__ == '__main__':
    unittest.main()
