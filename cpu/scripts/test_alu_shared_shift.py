from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
PARENT=PROJECT / 'experiments/alu_kept_precompute/rv32_alu.sv'
CORE=PROJECT / 'experiments/alu_shared_shift/rv32_alu.sv'
BASE_HASH='47E2A54401C1F3AEEC1E4F840682DC353B51FA20757634A46ACC6134A513BBB6'
ALU_HASH="3BF936686A69AEC18A3366EF0D7898E999D428E183B282E2C602E062E250DA7B"
SHIFT_BLOCK="    wire shift_left=operation==2;\n    wire [31:0] reversed_operand,shift_operand;\n    wire signed [32:0] extended_shift_operand;\n    wire [31:0] shifted_operand;\n    wire unused_shifted_sign;\n    wire [31:0] reversed_shifted,shift_result;\n    generate for(genvar shift_bit=0;shift_bit<32;shift_bit=shift_bit+1) begin: shift_reverse\n        assign reversed_operand[shift_bit]=operand_a[31-shift_bit];\n        assign reversed_shifted[shift_bit]=shifted_operand[31-shift_bit];\n    end endgenerate\n    assign shift_operand=shift_left ? reversed_operand : operand_a;\n    assign extended_shift_operand={operation==7 ? operand_a[31] : 1'b0,shift_operand};\n    assign {unused_shifted_sign,shifted_operand}=extended_shift_operand>>>operand_b[4:0];\n    assign shift_result=shift_left ? reversed_shifted : shifted_operand[31:0];\n"

class SharedShiftTests(unittest.TestCase):
    def simulate(self, source, top='alu_onehot_output_tb'):
        with tempfile.TemporaryDirectory(prefix='alu-shared-shift-') as temporary:
            directory=Path(temporary)
            candidate=directory / 'candidate.sv'
            dependencies=[]
            if top in ('alu_onehot_output_tb','alu_shared_shift_tb'):
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

    def test_exact_shared_shift_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),BASE_HASH)
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),ALU_HASH)
        source=CORE.read_text()
        self.assertEqual(source.count(SHIFT_BLOCK),1)
        restored=source.replace(SHIFT_BLOCK,'')
        restored=restored.replace('            2,6,7: result=shift_result;', '            2: result=operand_a<<operand_b[4:0];')
        restored=restored.replace('            8: result=operand_a|operand_b;', '            6: result=operand_a>>operand_b[4:0];'+chr(10)+'            7: result=$signed(operand_a)>>>operand_b[4:0];'+chr(10)+'            8: result=operand_a|operand_b;')
        self.assertEqual(restored,PARENT.read_text())

    def test_four_state_equivalence(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS onehot_output checks=53440',result.stdout)
        print(result.stdout.strip())

    def test_all_shift_positions_and_four_state_amounts(self):
        result=self.simulate(CORE.read_text(),'alu_shared_shift_tb')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS shared_shift checks=43008 data_checks=24576 amount_checks=18432',result.stdout)
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
            ('left_input_reverse','shift_operand=shift_left ? reversed_operand : operand_a','shift_operand=operand_a'),
            ('left_output_reverse','shift_result=shift_left ? reversed_shifted : shifted_operand[31:0]','shift_result=shifted_operand[31:0]'),
            ('arithmetic_sign',"operation==7 ? operand_a[31] : 1'b0", "1'b0"),
            ('logical_sign',"operation==7 ? operand_a[31] : 1'b0", 'operand_a[31]'),
            ('lost_signed_shift','wire signed [32:0] extended_shift_operand;','wire [32:0] extended_shift_operand;'),
            ('wrong_shift_amount','extended_shift_operand>>>operand_b[4:0]','extended_shift_operand>>>operand_a[4:0]'),
            ('missing_shift_case','2,6,7: result=shift_result;','2,6: result=shift_result;'),
            ('invalid_operation_leak','default: result=0;','default: result=shift_result;'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL onehot_output',result.stdout)
                print('PASS shared shift runtime rejection: '+name)

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
