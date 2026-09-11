import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from load_use_profile import file_hash
from regfile_valid_changes import CHANGES

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
CORE = ROOT / 'experiments/regfile_valid_reset/rv32_core.sv'


def wrapper(source, name):
    writes = re.findall(r'if\(([^\n]+)\) registers\[wb_rd\]<=([^;]+);', source)
    if len(writes) != 1:
        raise ValueError('Actual register data write is not unique')
    reads = re.findall(r'wire \[31:0\] (id_operand_[ab])=([^;]+);', source)
    if len(reads) != 2:
        raise ValueError('Actual register read ports missing')
    masked = 'reg [31:0] register_valid;' in source
    header = ['module '+name+'(input wire clk,rst_n,trace_write,input wire [4:0] wb_rd,id_rs1,id_rs2,input wire [31:0] wb_data,output wire [31:0] id_operand_a,id_operand_b);', 'reg [31:0] registers[0:31];', 'reg [31:0] register_valid;' if masked else 'integer reset_index;']
    header += ['assign '+port+'='+expression+';' for port,expression in reads]
    write = 'if('+writes[0][0]+') registers[wb_rd]<='+writes[0][1]+';'
    if masked:
        resets = re.findall(r'(?<!\])register_valid<=([^;]+);', source)
        marks = re.findall(r'if\(([^\n]+)\) register_valid\[wb_rd\]<=([^;]+);', source)
        if len(resets) != 1 or len(marks) != 1:
            raise ValueError('Actual validity state capture missing')
        body = ['always @(posedge clk) begin '+write+' end', 'always @(posedge clk or negedge rst_n) begin if(!rst_n) register_valid<='+resets[0]+'; else if('+marks[0][0]+') register_valid[wb_rd]<='+marks[0][1]+'; end']
    else:
        resets = re.findall(r'for\(reset_index=0;reset_index<32;reset_index=reset_index\+1\) registers\[reset_index\]<=([^;]+);', source)
        if len(resets) != 1:
            raise ValueError('Actual parent reset missing')
        body = ['always @(posedge clk or negedge rst_n) begin if(!rst_n) begin for(reset_index=0;reset_index<32;reset_index=reset_index+1) registers[reset_index]<='+resets[0]+'; end else begin '+write+' end end']
    return chr(10).join(header+body+['endmodule'])


class RegisterValidityTests(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix='regfile-valid-') as directory:
            work = Path(directory)
            design, image = work / 'design.sv', work / 'test.vvp'
            design.write_text(wrapper(PARENT.read_text(), 'parent_regfile')+chr(10)+wrapper(source, 'candidate_regfile'))
            compiled = subprocess.run(['iverilog','-g2012','-s','regfile_valid_tb','-o',str(image),str(design),str(ROOT / 'sim/regfile_valid_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=60)

    def test_exact_source_delta(self):
        self.assertEqual(file_hash(PARENT),'732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        self.assertEqual(file_hash(CORE),'EAEC82472D2A2DA28FC5BF9E9D5596CAEE9BB62DE1BFD064E2409846F276865C')
        source = CORE.read_text()
        for before,after in reversed(CHANGES):
            self.assertEqual(source.count(after),1)
            source = source.replace(after,before)
        self.assertEqual(source,PARENT.read_text())
        self.assertEqual(CORE.read_text().count('registers[wb_rd]<='),1)

    def test_actual_read_write_reset_equivalence(self):
        result = self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS regfile_valid',result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutations_rejected(self):
        source = CORE.read_text()
        changes = (
            ('wrong_reset','register_valid<=0;',"register_valid<=32'hffffffff;"),
            ('missing_valid_mark',"register_valid[wb_rd]<=1'b1;","register_valid[wb_rd]<=1'b0;"),
            ('wrong_write_data','registers[wb_rd]<=wb_data;','registers[wb_rd]<=~wb_data;'),
            ('raw_uninitialized_read',"(register_valid[id_rs1] ? registers[id_rs1] : 32'd0)",'registers[id_rs1]'),
            ('wrong_read_address',"register_valid[id_rs2] ? registers[id_rs2]","register_valid[id_rs1] ? registers[id_rs1]"),
            ('lost_read_bypass','(trace_write && wb_rd==id_rs1)',"(1'b0 && wb_rd==id_rs1)"),
            ('masked_wb_data',"? wb_data : (register_valid[id_rs1]","? 32'd0 : (register_valid[id_rs1]"),
        )
        for name,before,after in changes:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result = self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL regfile_valid',result.stdout+result.stderr)
                print('PASS register validity runtime rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
