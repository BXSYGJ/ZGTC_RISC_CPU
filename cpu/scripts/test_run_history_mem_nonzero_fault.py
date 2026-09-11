import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/run-history-mem-nonzero-stage'
CORE = ROOT / 'experiments/run_history_mem_nonzero/rv32_core.sv'
BENCH = ROOT / 'sim/run_history_mem_nonzero_fault_tb.sv'


class DirectReturnedFaultTests(unittest.TestCase):
    def test_fixture_only_adds_consistent_mem_state(self):
        source=BENCH.read_text()
        self.assertEqual(source.count(' dut.mem_rd_nonzero=dut.mem_rd!=0;'),1)
        restored=source.replace(' dut.mem_rd_nonzero=dut.mem_rd!=0;','')
        self.assertEqual(restored,(ROOT/'sim/wb_byte_retime_fault_tb.sv').read_text())

    def run_variant(self, source, overlap, bubble, accepted):
        self.assertEqual(hashlib.sha256((STAGE / 'rtl/rv32_alu.sv').read_bytes()).hexdigest().upper(), '3BF936686A69AEC18A3366EF0D7898E999D428E183B282E2C602E062E250DA7B')
        self.assertEqual((STAGE / 'rtl/rv32_alu.sv').read_bytes(), (ROOT / 'experiments/alu_shared_shift/rv32_alu.sv').read_bytes())
        with tempfile.TemporaryDirectory(prefix='early-direct-fault-') as temporary:
            directory = Path(temporary)
            candidate = directory / 'rv32_core.sv'
            candidate.write_text(source, encoding='utf-8')
            output = directory / 'test.vvp'
            dependencies = [STAGE / 'rtl' / (name + '.sv') for name in ('rv32_machine', 'rv32_decode', 'rv32_alu', 'rv32_btb', 'rv32_muldiv')]
            compilation = subprocess.run(['iverilog', '-g2012', '-s', 'raw_pair_retime_fault_tb', f'-Praw_pair_retime_fault_tb.FETCH_OVERLAP={overlap}', f'-Praw_pair_retime_fault_tb.LOAD_USE_BUBBLE={bubble}', '-o', str(output), str(candidate), *map(str, dependencies), str(BENCH)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            result = subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=60)
            if accepted:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS early_direct_fault checks=6 overlap={overlap} bubble={bubble}', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL early_direct_fault', result.stdout)
            print(result.stdout.strip())

    def test_source_and_fault_matrix(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), '8F03BA996C5CE58CBA3F8499796B240B6B903946435EEDA48444FD158782E6A2')
        self.assertEqual(CORE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())
        for overlap in (0, 1):
            for bubble in (0, 1):
                with self.subTest(overlap=overlap, bubble=bubble):
                    self.run_variant(CORE.read_text(), overlap, bubble, True)

    def test_returned_fault_mutants(self):
        original = CORE.read_text()
        mutations = (
            ('lost_bus_error', 'mem_exception || (mem_access && mem_sent && d_rsp_valid && d_rsp_error)', 'mem_exception'),
            ('wrong_fault_target', 'mem_flush ? (mem_fault ? trap_target : mem_next_pc) : early_next', 'mem_flush ? mem_next_pc : early_next'),
            ('fault_writeback', 'wb_valid<=mem_fire && !mem_fault;', 'wb_valid<=mem_fire;'),
            ('lost_pending_discard', 'if(fetch_active && !fetch_complete) fetch_discard<=1;', 'if(fetch_active && !fetch_complete) fetch_discard<=0;'),
        )
        for name, before, after in mutations:
            with self.subTest(name=name):
                self.assertIn(before, original)
                self.run_variant(original.replace(before, after), 1, 1, False)
                print('PASS rejected returned fault mutant: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
