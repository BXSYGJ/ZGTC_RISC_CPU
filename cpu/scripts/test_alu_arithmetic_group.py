from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
PARENT=PROJECT / 'experiments/alu_kept_precompute/rv32_alu.sv'
CORE=PROJECT / 'experiments/alu_arithmetic_group/rv32_alu.sv'
BASE_HASH='47E2A54401C1F3AEEC1E4F840682DC353B51FA20757634A46ACC6134A513BBB6'
ALU_HASH="A910BCDC5AA43124C05B1ADD6AA0E229A83081896BF764DAF1272BC83976641C"
OLD_HIGH="    wire [15:0] sum_high=sum_low[16] ? sum_high_one : sum_high_zero;\n    wire [15:0] difference_high=difference_low[16] ? difference_high_one : difference_high_zero;"
NEW_HIGH="    wire [16:0] arithmetic_low=operation[0] ? difference_low : sum_low;\n    (* syn_keep=1 *) wire [15:0] arithmetic_high_zero=operation[0] ? difference_high_zero : sum_high_zero;\n    (* syn_keep=1 *) wire [15:0] arithmetic_high_one=operation[0] ? difference_high_one : sum_high_one;\n    wire [15:0] arithmetic_high=arithmetic_low[16] ? arithmetic_high_one : arithmetic_high_zero;"
OLD_CASES="            0: result={sum_high,sum_low[15:0]};\n            1: result={difference_high,difference_low[15:0]};"
NEW_CASES="            0,1: result={arithmetic_high,arithmetic_low[15:0]};"

class ArithmeticGroupTests(unittest.TestCase):
    def simulate(self, source, top='alu_onehot_output_tb'):
        with tempfile.TemporaryDirectory(prefix='alu-arithmetic-group-') as temporary:
            directory=Path(temporary)
            candidate=directory / 'candidate.sv'
            dependencies=[]
            if top=='alu_onehot_output_tb':
                baseline=directory / 'baseline.sv'
                baseline.write_text(PARENT.read_text().replace('module rv32_alu (','module rv32_alu_baseline ('),encoding='utf-8')
                source=source.replace('module rv32_alu (','module rv32_alu_candidate (')
                dependencies.append(str(baseline))
            else:
                dependencies.append(str(PROJECT / 'build/wb-zero-byte-reduce-stage/rtl/rv32_decode.sv'))
            candidate.write_text(source,encoding='utf-8')
            image=directory / 'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s',top,'-o',str(image),str(candidate),*dependencies,str(PROJECT / 'sim' / (top+'.sv'))],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)

    def test_exact_arithmetic_group_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),BASE_HASH)
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),ALU_HASH)
        source=CORE.read_text()
        self.assertEqual(source.count(NEW_HIGH),1)
        self.assertEqual(source.count(NEW_CASES),1)
        self.assertEqual(source.replace(NEW_HIGH,OLD_HIGH).replace(NEW_CASES,OLD_CASES),PARENT.read_text())

    def test_four_state_equivalence(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS onehot_output checks=53440',result.stdout)
        print(result.stdout.strip())

    def test_independent_arithmetic_and_decode(self):
        for top,expected in (('alu_carry_select_tb','PASS carry_select checks=640'),('decode_alu_tb','PASS decode_alu checks=13124')):
            with self.subTest(top=top):
                result=self.simulate(CORE.read_text(),top)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn(expected,result.stdout)
                print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        preflight=self.simulate(source)
        self.assertEqual(preflight.returncode,0,preflight.stdout+preflight.stderr)
        mutations=(
            ('wrong_low_operation','arithmetic_low=operation[0] ? difference_low : sum_low','arithmetic_low=operation[0] ? sum_low : difference_low'),
            ('wrong_zero_operation','arithmetic_high_zero=operation[0] ? difference_high_zero : sum_high_zero','arithmetic_high_zero=operation[0] ? sum_high_zero : difference_high_zero'),
            ('wrong_one_operation','arithmetic_high_one=operation[0] ? difference_high_one : sum_high_one','arithmetic_high_one=operation[0] ? sum_high_one : difference_high_one'),
            ('lost_carry_borrow','arithmetic_low[16] ? arithmetic_high_one : arithmetic_high_zero','arithmetic_high_zero'),
            ('wrong_carry_bit','arithmetic_low[16] ?','arithmetic_low[15] ?'),
            ('lost_subtract_case','0,1: result=','0: result='),
            ('invalid_operation_leak','default: result=0;','default: result={arithmetic_high,arithmetic_low[15:0]};'),
            ('lost_shift_sign','7: result=$signed(operand_a)>>>operand_b[4:0];','7: result=operand_a>>operand_b[4:0];'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL onehot_output',result.stdout)
                print('PASS arithmetic group runtime rejection: '+name)

    def test_prior_masked_or_counterexample_is_retained(self):
        path=PROJECT / 'experiments/alu_onehot_output/masked_or_rejected.sv'
        self.assertEqual(sha256(path.read_bytes()).hexdigest().upper(),'A1CFC2B71578929CD4FFF5C76DB5964202654ADBD4C0A31130F1917A70BE1582')
        result=self.simulate(path.read_text())
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('FAIL onehot_output op=0110 first=z0000000 second=00000010',result.stdout)
        self.assertIn('expected=0000z000 actual=0000x000',result.stdout)
        print('PASS preserved masked OR Z-propagation rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
