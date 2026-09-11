from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/timer-increment-boundary-stage/rtl/rv32_core.sv'
CORE=ROOT/'experiments/id_relative_target/rv32_core.sv'
DECODE=ROOT/'build/timer-increment-boundary-stage/rtl/rv32_decode.sv'
CHANGES=[["    reg [31:0] ex_pc,ex_instruction,ex_prediction,ex_operand_a,ex_operand_b;","    reg [31:0] ex_pc,ex_instruction,ex_prediction,ex_operand_a,ex_operand_b;\n    reg [31:0] ex_relative_target;"],["    wire [31:0] early_target=ex_pc+ex_decode.immediate;","    wire [31:0] early_target=ex_relative_target;"],["        branch_target=ex_decode.is_jalr ? (effective_address & 32'hfffffffe) : ex_pc+ex_decode.immediate;","        branch_target=ex_decode.is_jalr ? (effective_address & 32'hfffffffe) : ex_relative_target;"],["            ex_pc<=0; ex_instruction<=0; ex_prediction<=0; ex_operand_a<=0; ex_operand_b<=0;","            ex_pc<=0; ex_instruction<=0; ex_prediction<=0; ex_operand_a<=0; ex_operand_b<=0;\n            ex_relative_target<=0;"],["                ex_error<=id_error; ex_decode<=id_decode; ex_rd<=id_rd;","                ex_error<=id_error; ex_decode<=id_decode; ex_rd<=id_rd;\n                ex_relative_target<=id_pc+id_decode.immediate;"]]


def wrapper(source,name):
    structures=re.findall(r'    typedef struct packed \{.*?    \} decode_t;',source,re.S)
    decoders=re.findall(r'    rv32_decode #\(\.ENABLE_M\(ENABLE_M\)\) decoder \(.*?\n    \);',source,re.S)
    if len(structures)!=1 or len(decoders)!=1:
        raise ValueError('Actual decode structure/instance is not unique')
    for signal,expected in {'ex_pc':['0','id_pc'],'ex_decode':['0','id_decode']}.items():
        if re.findall(r'\b'+signal+r'<=([^;]+);',source)!=expected:
            raise ValueError('Unexpected pipeline assignment: '+signal)
    transfer=re.search(r'            if\(id_fire\) begin\n                id_valid<=0;[^\n]+\n                ex_error<=id_error; ex_decode<=id_decode; ex_rd<=id_rd;(?P<target>\n                ex_relative_target<=[^;]+;)?',source)
    if transfer is None or 'ex_pc<=id_pc;' not in transfer.group():
        raise ValueError('PC/decode capture is not under actual ID transfer')
    candidate='reg [31:0] ex_relative_target;' in source
    reset=''
    capture=''
    if candidate:
        updates=re.findall(r'\bex_relative_target<=([^;]+);',source)
        if len(updates)!=2 or transfer.group('target') is None:
            raise ValueError('Unexpected relative-target state assignments')
        if not re.search(r'ex_operand_b<=0;\n            ex_relative_target<='+re.escape(updates[0])+r';',source):
            raise ValueError('Relative target reset is outside inspected reset region')
        reset='ex_relative_target<='+updates[0]+';'
        capture=transfer.group('target')
    early=re.findall(r'    wire \[31:0\] early_target=([^;]+);',source)
    branch=re.findall(r'        branch_target=([^;]+);',source)
    if len(early)!=1 or len(branch)!=1:
        raise ValueError('Actual target expression is not unique')
    return '\n'.join([
        'module '+name+'(input wire clk,rst_n,id_fire,input wire [31:0] id_pc,id_instruction,effective_address,output wire [31:0] target,indirect_target,pc,immediate);',
        'localparam ENABLE_M=1;',structures[0],decoders[0],
        'decode_t id_decode,ex_decode; wire [4:0] id_rs1,id_rs2,id_rd; reg [31:0] ex_pc;',
        'reg [31:0] ex_relative_target;' if candidate else '',
        'assign target='+early[0]+'; assign indirect_target='+branch[0]+';',
        'assign pc=ex_pc; assign immediate=ex_decode.immediate;',
        'always @(posedge clk or negedge rst_n) begin',
        'if(!rst_n) begin ex_pc<=0; ex_decode<=0; '+reset+' end',
        'else if(id_fire) begin ex_pc<=id_pc; ex_decode<=id_decode; '+capture+' end',
        'end','endmodule'])


class IdRelativeTargetTests(unittest.TestCase):
    def simulate(self,source):
        with tempfile.TemporaryDirectory(prefix='id-relative-target-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            image=directory/'test.vvp'
            design.write_text(wrapper(PARENT.read_text(),'relative_parent')+'\n'+wrapper(source,'relative_candidate'))
            compiled=subprocess.run(['iverilog','-g2012','-s','id_relative_target_tb','-o',str(image),str(design),str(DECODE),str(ROOT/'sim/id_relative_target_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)

    def test_exact_source_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'2807EB2F8E0B45F9AFA7F8DC8B4A65EBE8C209E59597A35932A79A39765E4D23')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'6273B0EE857DD0F9D38B1048E9F76D2BC5B6F888CBA986ED74723E16DB6C63F3')
        restored=CORE.read_text()
        for before,after in reversed(CHANGES):
            self.assertEqual(restored.count(after),1)
            restored=restored.replace(after,before)
        self.assertEqual(restored,PARENT.read_text())
        self.assertNotIn('ex_pc+ex_decode.immediate',CORE.read_text())
        self.assertIn("ex_decode.is_jalr ? (effective_address & 32'hfffffffe) : ex_relative_target",CORE.read_text())

    def test_actual_decoded_clocked_invariant(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS id_relative_target cycles=36864 resets=17',result.stdout)
        print(result.stdout.strip())

    def test_actual_runtime_mutants(self):
        source=CORE.read_text()
        variants=(
            ('wrong_reset','ex_relative_target<=0;','ex_relative_target<=4;'),
            ('stale_pc','ex_relative_target<=id_pc+id_decode.immediate;','ex_relative_target<=ex_pc+id_decode.immediate;'),
            ('stale_decode','ex_relative_target<=id_pc+id_decode.immediate;','ex_relative_target<=id_pc+ex_decode.immediate;'),
            ('lost_capture','ex_relative_target<=id_pc+id_decode.immediate;','ex_relative_target<=ex_relative_target;'),
            ('wrong_operation','ex_relative_target<=id_pc+id_decode.immediate;','ex_relative_target<=id_pc-id_decode.immediate;'),
            ('lost_carry','ex_relative_target<=id_pc+id_decode.immediate;','ex_relative_target<={id_pc[31:16]+id_decode.immediate[31:16],id_pc[15:0]+id_decode.immediate[15:0]};'),
            ('indirect_uses_relative',"(effective_address & 32'hfffffffe) : ex_relative_target","ex_relative_target : ex_relative_target"),
        )
        for name,before,after in variants:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL id_relative_target',result.stdout)
                print('PASS relative target runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
