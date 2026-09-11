import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class CacheRequestCapture(unittest.TestCase):
    def simulate(self, bits=16, readonly=0, fast_read=1, fast_write=1, overlap=1, variant='positive'):
        source_path = PROJECT / ('rtl/rv32_cache.sv' if variant == 'production' else
                                 'experiments/cache_split_index/rv32_cache.sv')
        source = source_path.read_text(encoding='utf-8')
        mutations = {
            'tag_zero': ('saved_request_tag<=req_address[ADDRESS_BITS-1:WORD_BITS+SET_BITS+2];', 'saved_request_tag<=0;'),
            'index_shift': ('request_index<=req_address[WORD_BITS+SET_BITS+1:2];', 'request_index<=req_address[WORD_BITS+SET_BITS:1];'),
            'alignment_zero': ('saved_request_alignment<=req_address[1:0];', 'saved_request_alignment<=0;'),
            'ignore_ready': ('if(req_valid && req_ready) begin', 'if(req_valid) begin'),
            'wrong_upper_extension': ("{{(32-ADDRESS_BITS){1'b0}},saved_request_tag,request_index,saved_request_alignment}", "{{(32-ADDRESS_BITS){1'b1}},saved_request_tag,request_index,saved_request_alignment}"),
        }
        if variant not in ('positive', 'production'):
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix='cache-request-capture-') as directory:
            work = Path(directory)
            rtl = work / 'rv32_cache.sv'
            rtl.write_text(source, encoding='utf-8')
            image = work / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'cache_tb', '-o', str(image),
                       f'-Pcache_tb.CHECK_REQUEST_CAPTURE={2 if variant == "production" else 1}', f'-Pcache_tb.ADDRESS_BITS={bits}',
                       f'-Pcache_tb.READONLY={readonly}', f'-Pcache_tb.FAST_READ_HIT={fast_read}',
                       f'-Pcache_tb.FAST_WRITE_HIT={fast_write}', f'-Pcache_tb.READ_OVERLAP={overlap}',
                       str(rtl), str(PROJECT / 'sim/cache_tb.sv')]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], text=True, capture_output=True, timeout=30)

    def test_all_modes_and_both_address_widths(self):
        for bits, readonly, fast_read, fast_write, overlap in itertools.product((16, 32), (0, 1), (0, 1), (0, 1), (0, 1)):
            with self.subTest(bits=bits, readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                result = self.simulate(bits, readonly, fast_read, fast_write, overlap)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('REQUEST_CAPTURE accepted=', result.stdout)
                self.assertIn('PASS cache', result.stdout)

    def test_restored_production_capture(self):
        for bits, readonly in itertools.product((16, 32), (0, 1)):
            with self.subTest(bits=bits, readonly=readonly):
                result = self.simulate(bits=bits, readonly=readonly, variant='production')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('REQUEST_CAPTURE accepted=', result.stdout)
                self.assertIn('PASS cache', result.stdout)

    def test_bad_field_or_qualification_controls(self):
        for variant in ('tag_zero', 'index_shift', 'alignment_zero', 'ignore_ready', 'wrong_upper_extension'):
            with self.subTest(variant=variant):
                result = self.simulate(variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL cache', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
