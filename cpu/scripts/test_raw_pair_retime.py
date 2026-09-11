from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/id-relative-target-stage/rtl/rv32_core.sv'
CORE=ROOT/'experiments/raw_pair_retime/rv32_core.sv'
CHANGES=[["    reg [31:0] ex_relative_target;","    reg [31:0] ex_relative_target;\n    reg [2:0] raw_pair_relation;"],["    wire [31:0] early_compare_left[0:5],early_compare_right[0:5];","    wire [31:0] early_compare_left[1:5],early_compare_right[1:5];"],["    assign early_compare_left[0]=ex_operand_a;\n    assign early_compare_right[0]=ex_operand_b;","    assign early_pair_result[0]=raw_pair_relation;"],["    genvar compare_pair,compare_byte;","    function automatic [2:0] operand_relation(input [31:0] operand_left,operand_right);\n        reg [3:0] byte_equal,byte_less;\n        reg unsigned_less;\n        integer byte_index;\n        begin\n            for(byte_index=0;byte_index<4;byte_index=byte_index+1) begin\n                byte_equal[byte_index]=operand_left[byte_index*8+:8]==operand_right[byte_index*8+:8];\n                byte_less[byte_index]=operand_left[byte_index*8+:8]<operand_right[byte_index*8+:8];\n            end\n            unsigned_less=parallel_less(byte_equal[3:1],byte_less);\n            operand_relation={&byte_equal,unsigned_less,\n                (operand_left[31]^operand_right[31]) ? operand_left[31] : unsigned_less};\n        end\n    endfunction\n    wire [31:0] id_operand_a=(trace_write && wb_rd==id_rs1) ? wb_data : registers[id_rs1];\n    wire [31:0] id_operand_b=(trace_write && wb_rd==id_rs2) ? wb_data : registers[id_rs2];\n    genvar compare_pair,compare_byte;"],["    generate for(compare_pair=0;compare_pair<6;compare_pair=compare_pair+1) begin: early_compare_pairs","    generate for(compare_pair=1;compare_pair<6;compare_pair=compare_pair+1) begin: early_compare_pairs"],["            ex_relative_target<=0;","            ex_relative_target<=0;\n            raw_pair_relation<=3'b100;"],["            if(ex_valid) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b; end","            if(ex_valid) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b; raw_pair_relation<=operand_relation(forwarded_a,forwarded_b); end"],["                ex_operand_a<=(trace_write && wb_rd==id_rs1) ? wb_data : registers[id_rs1];\n                ex_operand_b<=(trace_write && wb_rd==id_rs2) ? wb_data : registers[id_rs2];","                ex_operand_a<=id_operand_a;\n                ex_operand_b<=id_operand_b;\n                raw_pair_relation<=operand_relation(id_operand_a,id_operand_b);"]]


def wrapper(source,name):
    common=re.findall(r'    function automatic parallel_less\([^;]+;[\s\S]*?    endfunction',source)
    if len(common)!=1:
        raise ValueError('Actual byte comparison function is not unique')
    candidate='reg [2:0] raw_pair_relation;' in source
    refresh=re.findall(r'            if\(ex_valid\) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b;[^\n]* end',source)
    if len(refresh)!=1:
        raise ValueError('Actual EX operand refresh changed')
    resets={signal:re.findall(r'\b'+signal+r'<=([^;]+);',source) for signal in ('ex_operand_a','ex_operand_b')}
    if any(len(values)!=3 or values[0]!='0' or values[1]!='forwarded_'+side for side,values in (('a',resets['ex_operand_a']),('b',resets['ex_operand_b']))):
        raise ValueError('Unexpected actual EX operand update inventory')
    if source.index(refresh[0])>source.index('            if(id_fire) begin\n                id_valid<=0;'):
        raise ValueError('Actual ID override priority changed')
    capture_start=source.index('                ex_operand_a<=',source.index('            if(id_fire) begin\n                id_valid<=0;'))
    capture_end=source.index('\n',source.index('                ex_operand_b<=',capture_start))
    if candidate:
        capture_end=source.index('\n',source.index('                raw_pair_relation<=',capture_end))
    capture=source[capture_start:capture_end]
    expressions=[]
    reset_relation=''
    if candidate:
        function=re.findall(r'    function automatic \[2:0\] operand_relation\([^;]+;[\s\S]*?    endfunction',source)
        updates=re.findall(r'\braw_pair_relation<=([^;]+);',source)
        if len(function)!=1 or len(updates)!=3:
            raise ValueError('Actual relation function/state is not unique')
        reset_relation='raw_pair_relation<='+updates[0]+';'
        for side in ('a','b'):
            lines=re.findall(r'    wire \[31:0\] id_operand_'+side+r'=[^;]+;',source)
            if len(lines)!=1:
                raise ValueError('Actual ID operand selection is not unique')
            expressions.append(lines[0])
        logic='\n'.join([function[0],*expressions,'reg [2:0] raw_pair_relation; assign relation=raw_pair_relation;'])
    else:
        comparator=re.findall(r'    generate for\(compare_pair=0;compare_pair<6;compare_pair=compare_pair\+1\) begin: early_compare_pairs[\s\S]*?    end endgenerate',source)
        if len(comparator)!=1:
            raise ValueError('Actual original comparator is not unique')
        logic='\n'.join(['wire [31:0] early_compare_left[0:5],early_compare_right[0:5];','wire [2:0] early_pair_result[0:5]; genvar compare_pair,compare_byte;','assign early_compare_left[0]=ex_operand_a; assign early_compare_right[0]=ex_operand_b;',comparator[0].replace('compare_pair<6','compare_pair<1'),'assign relation=early_pair_result[0];'])
    result='\n'.join(['module '+name+'(input wire clk,rst_n,ex_valid,id_fire,trace_write,input wire [4:0] wb_rd,id_rs1,id_rs2,input wire [31:0] register_a,register_b,wb_data,forwarded_a,forwarded_b,output reg [31:0] ex_operand_a,ex_operand_b,output wire [2:0] relation);',common[0],logic,'always @(posedge clk or negedge rst_n) begin','if(!rst_n) begin ex_operand_a<=0; ex_operand_b<=0; '+reset_relation+' end','else begin',refresh[0],'if(id_fire) begin',capture,'end','end','end','endmodule'])
    return result.replace('registers[id_rs1]','register_a').replace('registers[id_rs2]','register_b')


class RawPairRetimeTests(unittest.TestCase):
    def simulate(self,source):
        with tempfile.TemporaryDirectory(prefix='raw-pair-retime-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            image=directory/'test.vvp'
            design.write_text(wrapper(PARENT.read_text(),'raw_pair_parent')+'\n'+wrapper(source,'raw_pair_candidate'))
            compiled=subprocess.run(['iverilog','-g2012','-s','raw_pair_retime_tb','-o',str(image),str(design),str(ROOT/'sim/raw_pair_retime_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=90)

    def test_exact_source_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'6273B0EE857DD0F9D38B1048E9F76D2BC5B6F888CBA986ED74723E16DB6C63F3')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'5AF1F525BD65B1F0471F5F0CF765B28B1717D70C2885393BC4E2E87F5CA7515C')
        restored=CORE.read_text()
        for before,after in reversed(CHANGES):
            self.assertEqual(restored.count(after),1)
            restored=restored.replace(after,before)
        self.assertEqual(restored,PARENT.read_text())

    def test_actual_clocked_operand_relation(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS raw_pair_retime cycles=32768 resets=17',result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutants(self):
        source=CORE.read_text()
        variants=(
            ('reset',"raw_pair_relation<=3'b100;","raw_pair_relation<=3'b000;"),
            ('stale_ex_refresh','raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);','raw_pair_relation<=raw_pair_relation;'),
            ('wrong_id_priority','raw_pair_relation<=operand_relation(id_operand_a,id_operand_b);','raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);'),
            ('stale_id','raw_pair_relation<=operand_relation(id_operand_a,id_operand_b);','raw_pair_relation<=operand_relation(ex_operand_a,ex_operand_b);'),
            ('reversed_refresh','raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);','raw_pair_relation<=operand_relation(forwarded_b,forwarded_a);'),
            ('signed_choice','? operand_left[31] : unsigned_less','? operand_right[31] : unsigned_less'),
            ('equality','operand_relation={&byte_equal,unsigned_less,','operand_relation={|byte_equal,unsigned_less,'),
            ('whole_width_four_state','unsigned_less=parallel_less(byte_equal[3:1],byte_less);','unsigned_less=operand_left<operand_right;'),
        )
        for name,before,after in variants:
            with self.subTest(name=name):
                if name=='whole_width_four_state':
                    function=re.findall(r'    function automatic \[2:0\] operand_relation\([^;]+;[\s\S]*?    endfunction',source)[0]
                    changed=source.replace(function,function.replace(before,after))
                else:
                    self.assertEqual(source.count(before),1)
                    changed=source.replace(before,after)
                result=self.simulate(changed)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL raw_pair_retime',result.stdout)
                print('PASS raw pair runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
