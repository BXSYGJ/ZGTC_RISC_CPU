import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'experiments/next_pc_enable_reduce/rv32_core.sv'
STAGE = ROOT / 'build/next-pc-enable-reduce-stage'
BENCH = ROOT / 'sim/early_direct_redirect_tb.sv'


class EarlyDirectRedirectTests(unittest.TestCase):
    def run_variant(self, source, overlap, accepted, bubble=1):
        with tempfile.TemporaryDirectory(prefix='early-direct-redirect-') as temporary:
            folder = Path(temporary)
            candidate = folder / 'rv32_core.sv'
            candidate.write_text(source, encoding='utf-8')
            output = folder / 'test.vvp'
            dependencies = [STAGE / 'rtl' / (name + '.sv') for name in ('rv32_machine','rv32_decode','rv32_alu','rv32_btb','rv32_muldiv')]
            compilation = subprocess.run(['iverilog','-g2012','-s','early_direct_redirect_tb',f'-Pearly_direct_redirect_tb.FETCH_OVERLAP={overlap}',f'-Pearly_direct_redirect_tb.LOAD_USE_BUBBLE={bubble}','-o',str(output),str(candidate),*map(str,dependencies),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            result = subprocess.run(['vvp',str(output)],capture_output=True,text=True,timeout=60)
            if accepted:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS early_direct_redirect checks=1080 early=42 older_priority=360 pending_drains=28 fallback={45 if bubble else 48} conditions=768 independent=8 overlap={overlap} bubble={bubble}', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL early_direct_redirect', result.stdout)
            print(result.stdout.strip())

    def test_canonical_and_staged_source(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), '79D70BDD0E9DAD5AC894799D30B9A5164D989C29B64D1D5B759992749D692B95')
        self.assertEqual(CORE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())

    def test_directed_redirect_matrix(self):
        for overlap in (0,1):
            for bubble in (0,1):
                with self.subTest(overlap=overlap,bubble=bubble):
                    self.run_variant(CORE.read_text(encoding='utf-8'), overlap, True, bubble)

    def test_runtime_mutants_are_rejected(self):
        original = CORE.read_text(encoding='utf-8')
        variants = (
            ('ignore_exception','ex_fire_without_irq && !early_local_exception &&','ex_fire_without_irq &&'),
            ('ignore_execute_ready','ex_fire_without_irq && !early_local_exception &&','!early_local_exception &&'),
            ('redirect_nonbranch','(ex_decode.is_branch || ex_decode.is_jal) && early_next','early_next'),
            ('allow_indirect','(ex_decode.is_branch || ex_decode.is_jal) && early_next','(ex_decode.is_branch || ex_decode.is_jal || ex_decode.is_jalr) && early_next'),
            ('ignore_load_dependency',' && !early_load_dependency &&',' &&'),
            ('invert_active_predicate','early_selected_condition^ex_instruction[12]','early_selected_condition^!ex_instruction[12]'),
            ('duplicate_mem_redirect','(!mem_early_redirect && mem_next_pc!=mem_prediction)','(mem_next_pc!=mem_prediction)'),
            ('wrong_older_target','mem_flush ? (mem_fault ? trap_target : mem_next_pc) : early_next','mem_flush ? mem_next_pc : early_next'),
            ('allow_younger_decode','!mem_flush && !ex_redirect_without_irq && !frontend_barrier','!mem_flush && !frontend_barrier'),
            ('lost_early_capture','mem_early_redirect<=ex_redirect;','mem_early_redirect<=0;'),
            ('allow_wrong_fetch_overlap','fetch_accept_space && !frontend_flush','fetch_accept_space && !mem_flush'),
            ('lost_pending_discard','if(fetch_active && !fetch_complete) fetch_discard<=1;','if(fetch_active && !fetch_complete) fetch_discard<=0;'),
        )
        for name,before,after in variants:
            with self.subTest(name=name):
                self.assertIn(before, original)
                self.run_variant(original.replace(before,after), 1, False)
                print('PASS rejected early redirect mutant: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
