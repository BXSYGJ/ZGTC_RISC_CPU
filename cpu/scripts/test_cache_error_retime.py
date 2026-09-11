import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/dcache-valid-banks-stage/rtl/rv32_cache.sv'
CANDIDATE = ROOT / 'experiments/cache_error_retime/rv32_cache.sv'


class ValidBanksTests(unittest.TestCase):
    def simulate(self, source, top, parameters):
        with tempfile.TemporaryDirectory(prefix='cache-error-retime-') as temporary:
            directory = Path(temporary)
            candidate = directory / 'rv32_cache.sv'
            reference = directory / 'rv32_cache_reference.sv'
            candidate.write_text(source, encoding='utf-8')
            reference.write_text(PARENT.read_text().replace('module rv32_cache #(', 'module rv32_cache_reference #(', 1), encoding='utf-8')
            output = directory / 'test.vvp'
            files = [candidate, reference, ROOT / 'sim' / (top + '.sv')]
            if top == 'cache_valid_banks_pairs_tb':
                files.append(ROOT / 'sim/cache_tb.sv')
            if top == 'cache_error_bounds_tb':
                files.append(PARENT.parent / 'rv32_burst_ram.sv')
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output)]
            command += [f'-P{top}.{name}={value}' for name, value in parameters.items()]
            command += list(map(str, files))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=180)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=60)

    def test_exact_source_delta(self):
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), 'A3B10973E0D24038B46FC8D387F400E6256B54CDD3027F21035B1EBCABFA9B9B')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), '984B45FECD7D5AFF9410638DD0234649F2BCB99198EC2933C761B7D6FD5C4343')
        original = PARENT.read_text()
        expected = original.replace('    output reg rsp_error,', '    output wire rsp_error,')
        expected = expected.replace('    reg [3:0] state;', '    reg [3:0] stored_state;\n    reg stored_rsp_error,request_check_pending;\n    reg [31:0] request_error_address;')
        expected = expected.replace('    reg request_write,request_missed,flushing,fill_failed;', '    reg request_write,request_missed,flushing,fill_failed;\n    wire request_input_error=request_check_pending && ((|request_error_address) || (READ_ONLY!=0 && request_write));\n    wire [3:0] state=request_input_error ? RESPONSE : stored_state;\n    assign rsp_error=request_input_error || stored_rsp_error;')
        expected = expected.replace('state<=', 'stored_state<=').replace('rsp_error<=', 'stored_rsp_error<=')
        expected = expected.replace('            stored_state<=IDLE; valid<=0; dirty<=0;', '            stored_state<=IDLE; valid<=0; dirty<=0;\n            request_check_pending<=0; request_error_address<=0;')
        expected = expected.replace('        end else begin\n            case(state)', '        end else begin\n            request_check_pending<=req_valid && req_ready;\n            if(request_input_error) stored_rsp_error<=1;\n            case(state)')
        expected = expected.replace('                RESPONSE: if(rsp_ready) stored_state<=IDLE;', '                RESPONSE: stored_state<=rsp_ready ? IDLE : RESPONSE;')
        expected = expected.replace('            if(req_ready) begin\n                request_address<=', "            if(req_ready) begin\n                request_error_address<=req_address & ((32'hffffffff<<ADDRESS_BITS) | 32'h3);\n                request_address<=")
        expected = expected.replace('                if((req_address >> ADDRESS_BITS)!=0 || req_address[1:0]!=0 || (READ_ONLY!=0 && req_write)) begin\n                    stored_rsp_error<=1; stored_state<=RESPONSE;\n                end else stored_state<=LOOKUP;', '                stored_state<=LOOKUP;')
        self.assertEqual(expected, CANDIDATE.read_text())

    def test_bounds_error_semantics(self):
        for address_bits, sets in ((10, 1), (16, 6)):
            for readonly in (0, 1):
                for fast in (0, 1):
                    for overlap in (0, 1):
                        parameters = dict(ADDRESS_BITS=address_bits, SET_BITS=sets, READ_ONLY=readonly, FAST_READ_HIT=fast, FAST_WRITE_HIT=fast, READ_OVERLAP=overlap)
                        with self.subTest(parameters=parameters):
                            outputs = []
                            for path in (PARENT, CANDIDATE):
                                result = self.simulate(path.read_text(), 'cache_error_bounds_tb', parameters)
                                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                                self.assertIn('PASS cache_error_bounds checks=', result.stdout)
                                outputs.append(result.stdout)
                            self.assertEqual(outputs[0], outputs[1])
                            print('PASS cache_error_retime bounds pair ' + str(parameters))

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
            ('missing_range_bit', "((32'hffffffff<<ADDRESS_BITS) | 32'h3)", "((32'hfffffffe<<ADDRESS_BITS) | 32'h3)"),
            ('missing_alignment', "((32'hffffffff<<ADDRESS_BITS) | 32'h3)", "(32'hffffffff<<ADDRESS_BITS)"),
            ('missing_pending', 'request_check_pending<=req_valid && req_ready;', "request_check_pending<=1'b0;"),
            ('missing_hold', 'RESPONSE: stored_state<=rsp_ready ? IDLE : RESPONSE;', 'RESPONSE: if(rsp_ready) stored_state<=IDLE;'),
            ('missing_sticky_error', 'if(request_input_error) stored_rsp_error<=1;', 'if(request_input_error) stored_rsp_error<=0;'),
            ('idle_check', 'request_check_pending<=req_valid && req_ready;', 'request_check_pending<=req_ready;'),
            ('readonly_write', ' || (READ_ONLY!=0 && request_write)', ''),
        )
        for name, before, after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before), 1)
                result = self.simulate(source.replace(before, after), 'cache_error_bounds_tb', dict(ADDRESS_BITS=16, SET_BITS=6, READ_ONLY=int(name=='readonly_write'), FAST_READ_HIT=1, FAST_WRITE_HIT=1, READ_OVERLAP=1))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL cache_error_bounds', result.stdout + result.stderr)
                self.assertNotIn('watchdog', result.stdout.lower() + result.stderr.lower())
                print('PASS cache_error_retime runtime mutant rejected: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
