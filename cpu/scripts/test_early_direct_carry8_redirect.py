import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'experiments/early_direct_carry8/rv32_core.sv'
STAGE = ROOT / 'build/early-direct-carry8-stage'
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
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), 'FCD29C622EFA23A666398EC27324A97A2291D1079A24CC6949FE91A74E1DFF99')
        self.assertEqual(CORE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())

    def test_directed_redirect_matrix(self):
        for overlap in (0,1):
            for bubble in (0,1):
                with self.subTest(overlap=overlap,bubble=bubble):
                    self.run_variant(CORE.read_text(encoding='utf-8'), overlap, True, bubble)

    def test_runtime_mutants_are_rejected(self):
        original = CORE.read_text(encoding='utf-8')
        variants = (
            ('ignore_exception','ex_fire && !early_exception &&','ex_fire &&'),
            ('ignore_execute_ready','ex_fire && !early_exception &&','!early_exception &&'),
            ('redirect_nonbranch',' && (ex_decode.is_branch || ex_decode.is_jal) &&',' &&'),
            ('allow_indirect','(ex_decode.is_branch || ex_decode.is_jal) && early_next','(ex_decode.is_branch || ex_decode.is_jal || ex_decode.is_jalr) && early_next'),
            ('ignore_load_dependency',' && !early_load_dependency &&',' &&'),
            ('returned_data_in_early_operand',"wire [31:0] early_operand_a=ex_rs1==0 || !ex_decode.uses_rs1 ? 32'b0 :\n        early_mem_forward && ex_rs1==mem_rd ? mem_result :\n        trace_write && ex_rs1==wb_rd ? wb_data : ex_operand_a;",'wire [31:0] early_operand_a=branch_operand_a;'),
            ('duplicate_mem_redirect','(!mem_early_redirect && mem_next_pc!=mem_prediction)','(mem_next_pc!=mem_prediction)'),
            ('wrong_older_target','mem_flush ? (mem_fault ? trap_target : mem_next_pc) : early_next','mem_flush ? mem_next_pc : early_next'),
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
