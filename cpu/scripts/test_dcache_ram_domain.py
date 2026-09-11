import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/early-direct-carry8-146250-stage'
PARENT = STAGE / 'rtl/rv32_memory_system.sv'
CANDIDATE = ROOT / 'experiments/dcache_ram_domain/rv32_memory_system.sv'


class MemoryDomainTests(unittest.TestCase):
    def simulate(self, source, top, parameters):
        with tempfile.TemporaryDirectory(prefix='dcache-ram-domain-') as temporary:
            directory = Path(temporary)
            memory = directory / 'rv32_memory_system.sv'
            memory.write_text(source, encoding='utf-8')
            output = directory / 'test.vvp'
            dependencies = [STAGE / 'rtl' / name for name in ('rv32_cache.sv', 'rv32_uncached.sv', 'rv32_burst_arbiter.sv', 'rv32_burst_ram.sv')]
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output)]
            command += [f'-P{top}.{name}={value}' for name, value in parameters.items()]
            command += [str(memory), *map(str, dependencies), str(ROOT / 'sim' / (top + '.sv'))]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=30)

    def test_exact_source_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), '2080990BFB20C6D6660EF63235E6C1716ED1DF1D1C4FD626A9B042E1CE86F2DD')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), '5463530856B489C99396AEBF14EAB2844DB21D9445EDD731CCCF676C0D2989F5')
        original = '    assign cache_req_address[1]=d_req_address;'
        replacement = "    assign cache_req_address[1]={4'b0,d_req_address[27:0]};"
        self.assertEqual(PARENT.read_text().count(original), 1)
        self.assertEqual(CANDIDATE.read_text().count(replacement), 1)
        self.assertTrue(PARENT.read_text().endswith('\n\n'))
        self.assertFalse(CANDIDATE.read_text().endswith('\n\n'))
        self.assertEqual(CANDIDATE.read_text().replace(replacement, original) + '\n', PARENT.read_text())

    def test_all_upper_nibbles_and_modes(self):
        for path in (PARENT, CANDIDATE):
            for cache in (0, 1):
                for overlap in (0, 1):
                    with self.subTest(source=str(path), cache=cache, overlap=overlap):
                        result = self.simulate(path.read_text(), 'memory_domain_tb', dict(ENABLE_CACHE=cache, DATA_OVERLAP=overlap))
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn(f'PASS memory_domain checks=1024 ram=64 mmio=960 cache={cache} overlap={overlap}', result.stdout)
                        print(result.stdout.strip())

    def test_exact_overlap_and_mmio_side_effects(self):
        for fast_read in (0, 1):
            for fast_write in (0, 1):
                for instruction_sets in (0, 3):
                    for stall in (0, 3, 7):
                        with self.subTest(read=fast_read, write=fast_write, sets=instruction_sets, stall=stall):
                            parameters = dict(DATA_OVERLAP=1, FAST_DCACHE_READ=fast_read, FAST_DCACHE_WRITE=fast_write, ICACHE_SET_BITS=instruction_sets, MMIO_STALL_CYCLES=stall)
                            outputs = []
                            for path in (PARENT, CANDIDATE):
                                result = self.simulate(path.read_text(), 'memory_overlap_tb', parameters)
                                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                                self.assertIn('PASS memory_overlap checks=', result.stdout)
                                self.assertIn('handovers=4', result.stdout)
                                outputs.append(result.stdout)
                            self.assertEqual(outputs[0], outputs[1])
                            print(f'PASS memory_domain paired overlap read={fast_read} write={fast_write} sets={instruction_sets} stall={stall}')

    def test_runtime_mutants(self):
        original = CANDIDATE.read_text()
        mutations = (
            ('clear_ram_bit24', "cache_req_address[1]={4'b0,d_req_address[27:0]}", "cache_req_address[1]={8'b0,d_req_address[23:0]}"),
            ('align_invalid_ram_request', "cache_req_address[1]={4'b0,d_req_address[27:0]}", "cache_req_address[1]={4'b0,d_req_address[27:2],2'b0}"),
            ('truncate_mmio_payload', 'mmio_request_address<=d_req_address;', 'mmio_request_address<=cache_req_address[1];'),
            ('miss_mmio_nibble', 'request_mmio=|d_req_address[31:28]', 'request_mmio=|d_req_address[31:29]'),
            ('send_mmio_to_ram', 'cache_req_valid[1]=d_req_valid && data_issue && !request_mmio;', 'cache_req_valid[1]=d_req_valid && data_issue;'),
        )
        for name, before, after in mutations:
            with self.subTest(name=name):
                self.assertEqual(original.count(before), 1)
                result = self.simulate(original.replace(before, after), 'memory_domain_tb', dict(ENABLE_CACHE=1, DATA_OVERLAP=1))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL memory_domain', result.stdout + result.stderr)
                self.assertNotIn('FAIL memory_domain coverage', result.stdout + result.stderr)
                print('PASS memory_domain runtime mutant rejected: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
