import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'build/late-forward-branch-stage/rtl/rv32_core.sv'
CORE=ROOT / 'experiments/late_branch_predicate/rv32_core.sv'
BENCH=ROOT / 'sim/late_branch_predicate_tb.sv'


class LateBranchPredicateTests(unittest.TestCase):
    def run_probe(self,source):
        begin=source.index('    wire early_mem_forward=')
        end=source.index('    wire [31:0] alu_a=',begin)
        block=source[begin:end].replace('ex_decode.uses_rs1','uses_rs1').replace('ex_decode.uses_rs2','uses_rs2')
        block=block.replace('ex_decode.is_branch','is_branch').replace('ex_decode.is_jal','is_jal')
        block=''.join(line+chr(10) for line in block.splitlines() if not line.startswith(('    wire [31:0] early_target=','    wire [31:0] early_next=','    wire early_exception=','    reg early_taken;')))
        for name in ('early_equal','early_unsigned_less','early_signed_less'):
            block=block.replace('wire '+name+'=','assign '+name+'=')
        for name in ('early_operand_a','early_operand_b'):
            block=block.replace('wire [31:0] '+name+'=','assign '+name+'=')
        wrapper="module early_compare_probe(input mem_valid,mem_writes,mem_load,mem_exception,trace_write,uses_rs1,uses_rs2,input [4:0] ex_rs1,ex_rs2,mem_rd,wb_rd,input [31:0] ex_operand_a,ex_operand_b,mem_result,wb_data,input is_branch,is_jal,input [2:0] funct3,output reg early_taken,output [31:0] early_operand_a,early_operand_b,output early_equal,early_unsigned_less,early_signed_less); wire [31:0] ex_instruction={17'b0,funct3,12'b0};"+chr(10)+block+'endmodule'+chr(10)
        with tempfile.TemporaryDirectory(prefix='late-wb-branch-') as temporary:
            folder=Path(temporary)
            probe=folder / 'probe.sv'
            probe.write_text(wrapper,encoding='utf-8')
            image=folder / 'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','late_branch_predicate_tb','-o',str(image),str(probe),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_only_compare_block_changes(self):
        parent=PARENT.read_text()
        source=CORE.read_text()
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'9689A65AF6BB16A2CB0DBE67B9A6540D60C2454C4524AA055087FA1550FFED35')
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),'CE62DD68B477DCD6C752A6FB8BAC3E3397A249AC6EA59E723CB6D14D518F462A')
        parent_begin=parent.index('    reg early_taken;')
        parent_end=parent.index('    wire [31:0] alu_a=',parent_begin)
        begin=source.index('    wire [2:0] early_condition_select=')
        end=source.index('    wire [31:0] alu_a=',begin)
        self.assertEqual(source[:begin]+parent[parent_begin:parent_end]+source[end:],parent)

    def test_original_and_candidate_against_independent_reference(self):
        outputs=[]
        for source in (PARENT,CORE):
            result=self.run_probe(source.read_text())
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS late_branch_predicate checks=589824 selectors=524288 random=65536 conditions=7077888',result.stdout)
            outputs.append(result.stdout)
            print(source.name+': '+result.stdout.strip())
        self.assertEqual(outputs[0],outputs[1])

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        preflight=self.run_probe(source)
        self.assertEqual(preflight.returncode,0,preflight.stdout+preflight.stderr)
        mutations=(
            ("mem_priority_a"," && !(early_mem_forward && ex_rs1==mem_rd) && trace_write"," && trace_write"),
            ("mem_priority_b"," && !(early_mem_forward && ex_rs2==mem_rd) && trace_write"," && trace_write"),
            ("same_source_predicate","&& branch_condition(3'b100,early_condition_select))","&& branch_condition(3'b000,early_condition_select))"),
            ("reverse_signed_mem_wb","!early_pair_result[5][2] && !early_pair_result[5][0]","!early_pair_result[5][2] && early_pair_result[5][0]"),
            ("wrong_mem_selection","early_source_a[2] && early_source_b[1] && early_pair_condition[1]","early_source_a[2] && early_source_b[1] && early_pair_condition[2]"),
            ("zero_right_signed","branch_condition({early_data_zero[0],1'b0,ex_operand_a[31]},early_condition_select)","branch_condition({early_data_zero[0],1'b0,!ex_operand_a[31]},early_condition_select)"),
            ("wrong_wb_pair","assign early_compare_right[4]=wb_data;","assign early_compare_right[4]=mem_result;"),
            ("wrong_pair_sign","? early_compare_left[compare_pair][31] : unsigned_less","? early_compare_right[compare_pair][31] : unsigned_less"),
            ("invert_condition","early_selected_condition^ex_instruction[12]","early_selected_condition^!ex_instruction[12]"),
            ("illegal_condition","(|early_condition_select) && (early_selected_condition^ex_instruction[12])","early_selected_condition^ex_instruction[12]"),
            ("signed_unsigned_decode","ex_instruction[14:13]==2'b11,ex_instruction[14:13]==2'b10","ex_instruction[14:13]==2'b10,ex_instruction[14:13]==2'b11"),
            ("ignore_unused_a","wire early_zero_a=ex_rs1==0 || !ex_decode.uses_rs1;","wire early_zero_a=ex_rs1==0;"),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_probe(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL late_branch_predicate',result.stdout)
                print('PASS late-forward runtime rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
