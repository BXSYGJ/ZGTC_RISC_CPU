import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT / 'build/late-wb-branch-stage/rtl/rv32_core.sv'
CORE=ROOT / 'experiments/late_forward_branch_select/rv32_core.sv'
BENCH=ROOT / 'sim/late_wb_branch_tb.sv'


class LateForwardCompareTests(unittest.TestCase):
    def run_probe(self,source):
        begin=source.index('    wire early_mem_forward=')
        end=source.index('    reg early_taken;',begin)
        block=source[begin:end].replace('ex_decode.uses_rs1','uses_rs1').replace('ex_decode.uses_rs2','uses_rs2')
        for name in ('early_equal','early_unsigned_less','early_signed_less'):
            block=block.replace('wire '+name+'=','assign '+name+'=')
        for name in ('early_operand_a','early_operand_b'):
            block=block.replace('wire [31:0] '+name+'=','assign '+name+'=')
        wrapper='module early_compare_probe(input mem_valid,mem_writes,mem_load,mem_exception,trace_write,uses_rs1,uses_rs2,input [4:0] ex_rs1,ex_rs2,mem_rd,wb_rd,input [31:0] ex_operand_a,ex_operand_b,mem_result,wb_data,output [31:0] early_operand_a,early_operand_b,output early_equal,early_unsigned_less,early_signed_less);'+chr(10)+block+'endmodule'+chr(10)
        with tempfile.TemporaryDirectory(prefix='late-wb-branch-') as temporary:
            folder=Path(temporary)
            probe=folder / 'probe.sv'
            probe.write_text(wrapper,encoding='utf-8')
            image=folder / 'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','late_wb_branch_tb','-o',str(image),str(probe),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_only_compare_block_changes(self):
        parent=PARENT.read_text()
        source=CORE.read_text()
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'6741A6D0569E47CF1FE8B2BA9862692011CFE13941AE9F971B252C95A34B7364')
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(),'9689A65AF6BB16A2CB0DBE67B9A6540D60C2454C4524AA055087FA1550FFED35')
        parent_begin=parent.index('    wire early_wb_a=')
        parent_end=parent.index('    reg early_taken;',parent_begin)
        begin=source.index('    wire [3:0] early_source_a,early_source_b;')
        end=source.index('    reg early_taken;',begin)
        self.assertEqual(source[:begin]+parent[parent_begin:parent_end]+source[end:],parent)

    def test_original_and_candidate_against_independent_reference(self):
        outputs=[]
        for source in (PARENT,CORE):
            result=self.run_probe(source.read_text())
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS late_wb_branch checks=589824 selectors=524288 random=65536',result.stdout)
            outputs.append(result.stdout)
            print(source.name+': '+result.stdout.strip())
        self.assertEqual(outputs[0],outputs[1])

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        preflight=self.run_probe(source)
        self.assertEqual(preflight.returncode,0,preflight.stdout+preflight.stderr)
        mutations=(
            ('mem_priority_a',' && !(early_mem_forward && ex_rs1==mem_rd) && trace_write',' && trace_write'),
            ('mem_priority_b',' && !(early_mem_forward && ex_rs2==mem_rd) && trace_write',' && trace_write'),
            ('same_source_identity'," & 3'b100)"," & 3'b000)"),
            ('reverse_signed_mem_wb','!early_pair_result[5][2] && !early_pair_result[5][0]','!early_pair_result[5][2] && early_pair_result[5][0]'),
            ('zero_left_unsigned','{early_data_zero[1],!early_data_zero[1],','{early_data_zero[1],early_data_zero[1],'),
            ('zero_right_signed',"{early_data_zero[0],1'b0,ex_operand_a[31]}","{early_data_zero[0],1'b0,!ex_operand_a[31]}"),
            ('wrong_mem_pair','assign early_compare_left[1]=mem_result;','assign early_compare_left[1]=wb_data;'),
            ('wrong_wb_pair','assign early_compare_right[4]=wb_data;','assign early_compare_right[4]=mem_result;'),
            ('wrong_pair_sign','? early_compare_left[compare_pair][31] : unsigned_less','? early_compare_right[compare_pair][31] : unsigned_less'),
            ('ignore_unused_a','wire early_zero_a=ex_rs1==0 || !ex_decode.uses_rs1;','wire early_zero_a=ex_rs1==0;'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_probe(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL late_wb_branch check=',result.stdout)
                print('PASS late-forward runtime rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
