from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'experiments/wb_zero_byte_reduce/rv32_core.sv'
CANDIDATE=ROOT/'experiments/forward_select_maxfan/rv32_core.sv'
OLD_BLOCK="    always @* begin\n        forwarded_a=ex_operand_a; forwarded_b=ex_operand_b;\n        if(wb_valid && wb_writes && wb_rd!=0) begin\n            if(ex_rs1==wb_rd) forwarded_a=wb_data;\n            if(ex_rs2==wb_rd) forwarded_b=wb_data;\n        end\n        if(mem_valid && mem_writes && mem_rd!=0 && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0)) begin\n            if(ex_rs1==mem_rd) forwarded_a=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;\n            if(ex_rs2==mem_rd) forwarded_b=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;\n        end\n        if(ex_rs1==0 || !ex_decode.uses_rs1) forwarded_a=0;\n        if(ex_rs2==0 || !ex_decode.uses_rs2) forwarded_b=0;\n    end\n"
NEW_BLOCK="    (* syn_maxfan=24 *) wire execute_mem_forward_a=mem_valid && mem_writes && mem_rd!=0 && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs1==mem_rd;\n    (* syn_maxfan=24 *) wire execute_mem_forward_b=mem_valid && mem_writes && mem_rd!=0 && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs2==mem_rd;\n    always @* begin\n        forwarded_a=ex_operand_a; forwarded_b=ex_operand_b;\n        if(wb_valid && wb_writes && wb_rd!=0) begin\n            if(ex_rs1==wb_rd) forwarded_a=wb_data;\n            if(ex_rs2==wb_rd) forwarded_b=wb_data;\n        end\n        if(execute_mem_forward_a) forwarded_a=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;\n        if(execute_mem_forward_b) forwarded_b=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;\n        if(ex_rs1==0 || !ex_decode.uses_rs1) forwarded_a=0;\n        if(ex_rs2==0 || !ex_decode.uses_rs2) forwarded_b=0;\n    end\n"


def wrapper(source,name):
    block=re.findall(r'    always @\* begin\n        forwarded_a=[\s\S]*?\n    end\n',source)
    if len(block)!=1:
        raise ValueError('Ambiguous actual forwarding block')
    declarations='\n'.join(line for line in source.splitlines() if 'wire execute_mem_forward_' in line)
    return '\n'.join([
        'module '+name+' #(parameter integer LOAD_USE_BUBBLE=1)(',
        'input wire [7:0] controls, input wire [4:0] ex_rs1,ex_rs2,mem_rd,wb_rd,',
        'input wire [31:0] ex_operand_a,ex_operand_b,mem_result,mem_value,wb_data,',
        'output reg [31:0] forwarded_a,forwarded_b);',
        'wire wb_valid=controls[0],wb_writes=controls[1],mem_valid=controls[2],mem_writes=controls[3],mem_load=controls[4],mem_exception=controls[6];',
        'typedef struct packed { logic uses_rs1,uses_rs2; } decode_t;',
        'wire decode_t ex_decode={controls[5],controls[7]};',
        declarations,block[0],'endmodule'])


class ForwardMaxfanTests(unittest.TestCase):
    def simulate(self,source):
        with tempfile.TemporaryDirectory(prefix='forward-maxfan-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            image=directory/'test.vvp'
            design.write_text(wrapper(PARENT.read_text(),'forward_parent')+'\n'+wrapper(source,'forward_candidate'))
            compiled=subprocess.run(['iverilog','-g2012','-s','forward_select_maxfan_tb','-o',str(image),str(design),str(ROOT/'sim/forward_select_maxfan_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=90)

    def test_exact_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'C071A22D1579A40D3A9D972F85F86BDBED32FBAD3647D62CFB292C0876F9EB43')
        self.assertEqual(sha256(CANDIDATE.read_bytes()).hexdigest().upper(),'4A5BA5768E0FC87B43C349454A7CD176A4B0DE2B503C45931FAC1F35E3BB0D77')
        candidate=CANDIDATE.read_text()
        self.assertEqual(candidate.count(NEW_BLOCK),1)
        self.assertEqual(candidate.replace(NEW_BLOCK,OLD_BLOCK),PARENT.read_text())
        self.assertEqual(candidate.count('syn_maxfan=24'),2)

    def test_four_state_priority_equivalence(self):
        result=self.simulate(CANDIDATE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS forward_select checks=168000',result.stdout)
        print(result.stdout.strip())

    def test_runtime_rejections(self):
        source=CANDIDATE.read_text()
        mutations=(
            ('missing_exception',' && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs1==mem_rd',' && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs1==mem_rd'),
            ('wrong_register',"(* syn_maxfan=24 *) wire execute_mem_forward_a=mem_valid && mem_writes && mem_rd!=0 && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs1==mem_rd;","(* syn_maxfan=24 *) wire execute_mem_forward_a=mem_valid && mem_writes && mem_rd!=0 && !mem_exception && (!mem_load || LOAD_USE_BUBBLE==0) && ex_rs1==wb_rd;"),
            ('lost_zero_a','if(ex_rs1==0 || !ex_decode.uses_rs1) forwarded_a=0;','if(!ex_decode.uses_rs1) forwarded_a=0;'),
            ('wrong_load_bubble','forwarded_a=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;','forwarded_a=mem_value;'),
            ('lost_mem_priority','if(execute_mem_forward_b) forwarded_b=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;','if(execute_mem_forward_b) forwarded_b=wb_data;'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL forward_select',result.stdout)
                print('PASS forwarding runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
