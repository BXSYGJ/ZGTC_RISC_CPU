from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'experiments/wb_zero_byte_reduce/rv32_core.sv'
CORE=ROOT/'experiments/forward_match_retime/rv32_core.sv'
MATCH_BLOCK="            if(id_fire) begin\n                if(ex_fire) begin\n                    mem_match_a<=id_rs1==ex_rd;\n                    mem_match_b<=id_rs2==ex_rd;\n                end else begin\n                    mem_match_a<=id_rs1==mem_rd;\n                    mem_match_b<=id_rs2==mem_rd;\n                end\n            end else if(ex_fire) begin\n                mem_match_a<=ex_rs1==ex_rd;\n                mem_match_b<=ex_rs2==ex_rd;\n            end\n"


def wrapper(source,name):
    expected_updates={'ex_instruction':['0','id_instruction'],'ex_rd':['0','id_rd'],'mem_rd':['0','ex_rd']}
    for signal,expected in expected_updates.items():
        if re.findall(r'\b'+signal+r'<=([^;]+);',source)!=expected:
            raise ValueError('Unexpected actual pipeline register updates: '+signal)
    if not re.search(r'if\(ex_fire\) begin\s+ex_valid<=0;[^\n]+\n[^\n]+\n[^\n]*mem_rd<=ex_rd;',source):
        raise ValueError('MEM destination outside inspected EX transfer')
    if not re.search(r'if\(id_fire\) begin\s+id_valid<=0;[^\n]*ex_instruction<=id_instruction;[^\n]*\n[^\n]*ex_rd<=id_rd;',source):
        raise ValueError('EX registers outside inspected ID transfer')
    candidate='reg mem_match_a,mem_match_b;' in source
    flags=''
    reset_flags=''
    if candidate:
        begin=source.index('            if(id_fire) begin\n                if(ex_fire) begin')
        end=source.index('            if(id_fire) begin\n                id_valid<=0;',begin)
        flags=source[begin:end]
        for signal in ('mem_match_a','mem_match_b'):
            updates=re.findall(r'\b'+signal+r'<=([^;]+);',source)
            if len(updates)!=4:
                raise ValueError('Unexpected match state updates')
            reset_flags+=signal+'<='+updates[0]+';'
    return '\n'.join([
        'module '+name+'(input wire clk,rst_n,id_fire,ex_fire,input wire [31:0] id_instruction,output reg [31:0] ex_instruction,output reg [4:0] ex_rd,mem_rd,output wire match_a,match_b);',
        'wire [4:0] id_rs1=id_instruction[19:15],id_rs2=id_instruction[24:20],id_rd=id_instruction[11:7];',
        'wire [4:0] ex_rs1=ex_instruction[19:15],ex_rs2=ex_instruction[24:20];',
        'reg mem_match_a,mem_match_b;' if candidate else '',
        'assign match_a='+('mem_match_a' if candidate else 'ex_rs1==mem_rd')+';',
        'assign match_b='+('mem_match_b' if candidate else 'ex_rs2==mem_rd')+';',
        'always @(posedge clk or negedge rst_n) begin',
        'if(!rst_n) begin ex_instruction<=0; ex_rd<=0; mem_rd<=0; '+reset_flags+' end',
        'else begin',
        'if(ex_fire) mem_rd<=ex_rd;',
        'if(id_fire) begin ex_instruction<=id_instruction; ex_rd<=id_rd; end',
        flags,'end','end','endmodule'])


class ForwardMatchRetimeTests(unittest.TestCase):
    def simulate(self,source):
        with tempfile.TemporaryDirectory(prefix='forward-match-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            image=directory/'test.vvp'
            design.write_text(wrapper(PARENT.read_text(),'match_parent')+'\n'+wrapper(source,'match_candidate'))
            compiled=subprocess.run(['iverilog','-g2012','-s','forward_match_retime_tb','-o',str(image),str(design),str(ROOT/'sim/forward_match_retime_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)

    def test_exact_retimed_state_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'C071A22D1579A40D3A9D972F85F86BDBED32FBAD3647D62CFB292C0876F9EB43')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'2807EB2F8E0B45F9AFA7F8DC8B4A65EBE8C209E59597A35932A79A39765E4D23')
        source=CORE.read_text()
        self.assertEqual(source.count(MATCH_BLOCK),1)
        restored=source.replace(MATCH_BLOCK,'').replace('    reg mem_match_a,mem_match_b;\n','').replace(' mem_match_a<=1; mem_match_b<=1;','')
        self.assertEqual(restored.count('mem_match_a'),9)
        self.assertEqual(restored.count('mem_match_b'),8)
        restored=restored.replace('mem_match_a','ex_rs1==mem_rd').replace('mem_match_b','ex_rs2==mem_rd')
        self.assertEqual(restored,PARENT.read_text())
        decode=(ROOT/'build/alu-shared-shift-stage/rtl/rv32_decode.sv').read_text()
        for assignment in ('assign rs1 = instruction[19:15];','assign rs2 = instruction[24:20];','assign rd = instruction[11:7];'):
            self.assertIn(assignment,decode)

    def test_actual_clocked_match_invariant(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS forward_match cycles=20480 resets=9 binary_cycles=4096 four_state_cycles=16384',result.stdout)
        print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        mutations=(
            ('wrong_reset','mem_match_a<=1;','mem_match_a<=0;'),
            ('stale_mem_on_joint_transfer','mem_match_a<=id_rs1==ex_rd;','mem_match_a<=id_rs1==mem_rd;'),
            ('old_ex_on_id_only','mem_match_a<=id_rs1==mem_rd;','mem_match_a<=ex_rs1==mem_rd;'),
            ('missed_ex_only','mem_match_a<=ex_rs1==ex_rd;','mem_match_a<=mem_match_a;'),
            ('wrong_source_b','mem_match_b<=id_rs2==ex_rd;','mem_match_b<=id_rs1==ex_rd;'),
            ('wrong_mem_b_hold','mem_match_b<=id_rs2==mem_rd;','mem_match_b<=id_rs2==ex_rd;'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL forward_match',result.stdout)
                print('PASS retimed match runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
