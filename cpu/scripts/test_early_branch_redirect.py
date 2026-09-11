import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'experiments/early_branch_redirect/rv32_core.sv'
STAGE = ROOT / 'build/early-branch-redirect-stage'
BENCH = ROOT / 'sim/early_branch_redirect_tb.sv'


class EarlyBranchRedirectTests(unittest.TestCase):
    def run_variant(self, source, overlap, accepted):
        with tempfile.TemporaryDirectory(prefix='early-branch-redirect-') as temporary:
            folder = Path(temporary)
            candidate = folder / 'rv32_core.sv'
            candidate.write_text(source, encoding='utf-8')
            output = folder / 'test.vvp'
            dependencies = [STAGE / 'rtl' / (name + '.sv') for name in ('rv32_machine','rv32_decode','rv32_alu','rv32_btb','rv32_muldiv')]
            compilation = subprocess.run(['iverilog','-g2012','-s','early_branch_redirect_tb',f'-Pearly_branch_redirect_tb.FETCH_OVERLAP={overlap}','-o',str(output),str(candidate),*map(str,dependencies),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            result = subprocess.run(['vvp',str(output)],capture_output=True,text=True,timeout=60)
            if accepted:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS early_redirect checks=810 early=36 older_priority=360 pending_drains=24 overlap={overlap}', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL early_redirect', result.stdout)
            print(result.stdout.strip())

    def test_canonical_and_staged_source(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), '40A6F85019055DAE2AA8A8763E9425FA21DB49AB6533B1968844689EDA8DB5FE')
        self.assertEqual(CORE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())

    def test_directed_redirect_matrix(self):
        for overlap in (0,1):
            with self.subTest(overlap=overlap):
                self.run_variant(CORE.read_text(encoding='utf-8'), overlap, True)

    def test_runtime_mutants_are_rejected(self):
        original = CORE.read_text(encoding='utf-8')
        variants = (
            ('ignore_exception','ex_fire && !execute_exception &&','ex_fire &&'),
            ('ignore_execute_ready','ex_fire && !execute_exception &&','!execute_exception &&'),
            ('redirect_nonbranch',' && (ex_decode.is_branch || ex_decode.is_jal || ex_decode.is_jalr) &&',' &&'),
            ('duplicate_mem_redirect','(!mem_early_redirect && mem_next_pc!=mem_prediction)','(mem_next_pc!=mem_prediction)'),
            ('wrong_older_target','mem_flush ? (mem_fault ? trap_target : mem_next_pc) : actual_next','mem_flush ? mem_next_pc : actual_next'),
            ('allow_younger_decode','id_fire=id_valid && ex_ready && !frontend_flush','id_fire=id_valid && ex_ready && !mem_flush'),
            ('lost_early_capture','mem_early_redirect<=ex_redirect;','mem_early_redirect<=0;'),
            ('allow_wrong_fetch_overlap','FETCH_OVERLAP!=0 && fetch_complete && !frontend_flush','FETCH_OVERLAP!=0 && fetch_complete && !mem_flush'),
            ('lost_pending_discard','if(fetch_active && !fetch_complete) fetch_discard<=1;','if(fetch_active && !fetch_complete) fetch_discard<=0;'),
        )
        for name,before,after in variants:
            with self.subTest(name=name):
                self.assertIn(before, original)
                self.run_variant(original.replace(before,after), 1, False)
                print('PASS rejected early redirect mutant: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
