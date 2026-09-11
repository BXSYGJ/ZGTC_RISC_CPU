from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_raw_pair_retime import wrapper as raw_wrapper

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/predictor-index-maxfan-stage/rtl/rv32_core.sv'
CORE = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
CHANGES = [["    reg [2:0] raw_pair_relation;","    reg [2:0] raw_pair_relation;\n    reg [3:0] wb_a_byte_equal,wb_a_byte_less,wb_b_byte_equal,wb_b_byte_less;\n    reg [31:0] compare_next_a,compare_next_b,compare_next_wb;\n    integer wb_compare_byte;"],["    genvar compare_pair,compare_byte;","    always @* begin\n        compare_next_a=ex_operand_a;\n        compare_next_b=ex_operand_b;\n        compare_next_wb=wb_data;\n        if(ex_valid) begin compare_next_a=forwarded_a; compare_next_b=forwarded_b; end\n        if(id_fire) begin compare_next_a=id_operand_a; compare_next_b=id_operand_b; end\n        if(mem_fire && !mem_fault) compare_next_wb=mem_value;\n    end\n    always @(posedge clk or negedge rst_n) begin\n        if(!rst_n) begin\n            wb_a_byte_equal<=4'b1111; wb_a_byte_less<=0;\n            wb_b_byte_equal<=4'b1111; wb_b_byte_less<=0;\n        end else begin\n            for(wb_compare_byte=0;wb_compare_byte<4;wb_compare_byte=wb_compare_byte+1) begin\n                wb_a_byte_equal[wb_compare_byte]<=compare_next_a[wb_compare_byte*8+:8]==compare_next_wb[wb_compare_byte*8+:8];\n                wb_a_byte_less[wb_compare_byte]<=compare_next_a[wb_compare_byte*8+:8]<compare_next_wb[wb_compare_byte*8+:8];\n                wb_b_byte_equal[wb_compare_byte]<=compare_next_wb[wb_compare_byte*8+:8]==compare_next_b[wb_compare_byte*8+:8];\n                wb_b_byte_less[wb_compare_byte]<=compare_next_wb[wb_compare_byte*8+:8]<compare_next_b[wb_compare_byte*8+:8];\n            end\n        end\n    end\n    genvar compare_pair,compare_byte;"],["        for(compare_byte=0;compare_byte<4;compare_byte=compare_byte+1) begin: bytes\n            assign byte_equal[compare_byte]=early_compare_left[compare_pair][compare_byte*8+:8]==early_compare_right[compare_pair][compare_byte*8+:8];\n            assign byte_less[compare_byte]=early_compare_left[compare_pair][compare_byte*8+:8]<early_compare_right[compare_pair][compare_byte*8+:8];\n        end","        if(compare_pair==2) begin: wb_left\n            assign byte_equal=wb_b_byte_equal;\n            assign byte_less=wb_b_byte_less;\n        end else if(compare_pair==4) begin: wb_right\n            assign byte_equal=wb_a_byte_equal;\n            assign byte_less=wb_a_byte_less;\n        end else begin: direct_pair\n            for(compare_byte=0;compare_byte<4;compare_byte=compare_byte+1) begin: bytes\n                assign byte_equal[compare_byte]=early_compare_left[compare_pair][compare_byte*8+:8]==early_compare_right[compare_pair][compare_byte*8+:8];\n                assign byte_less[compare_byte]=early_compare_left[compare_pair][compare_byte*8+:8]<early_compare_right[compare_pair][compare_byte*8+:8];\n            end\n        end"]]


def wrapper(source, name):
    result = raw_wrapper(source, name)
    before = 'input wire [31:0] register_a,register_b,wb_data,forwarded_a,forwarded_b,'
    if result.count(before) != 1:
        raise ValueError('Unexpected original wrapper operands')
    result = result.replace(before, 'input wire [31:0] register_a,register_b,forwarded_a,forwarded_b,mem_value,input wire mem_fire,mem_fault,output reg [31:0] wb_data,output wire [2:0] wb_a_relation,wb_b_relation,')
    captures = re.findall(r'            if\(mem_fire && !mem_fault\) begin\n                wb_pc<=mem_pc;[^\n]*wb_data<=([^;]+);\n            end', source)
    assignments = re.findall(r'\bwb_data<=([^;]+);', source)
    if captures != ['mem_value'] or assignments != ['0', 'mem_value']:
        raise ValueError('Actual WB capture/reset changed')
    comparator = re.findall(r'    generate for\(compare_pair=1;compare_pair<6;compare_pair=compare_pair\+1\) begin: early_compare_pairs[\s\S]*?    end endgenerate', source)
    if len(comparator) != 1:
        raise ValueError('Actual comparison generate changed')
    bindings = re.findall(r'    assign early_compare_(?:left|right)\[[1-5]\]=[^;]+;', source)
    if len(bindings) != 10:
        raise ValueError('Actual comparator input inventory changed')
    extra = []
    if 'reg [3:0] wb_a_byte_equal' in source:
        state = re.findall(r'    reg \[3:0\] wb_a_byte_equal[^;]+;\n    reg \[31:0\] compare_next_a[^;]+;\n    integer wb_compare_byte;', source)
        start = source.index('    always @* begin\n        compare_next_a=')
        end = source.index('    genvar compare_pair,compare_byte;', start)
        if len(state) != 1:
            raise ValueError('Actual byte comparison state changed')
        extra.extend([state[0], source[start:end]])
    extra.extend(['wire [31:0] mem_result=0;', 'wire [31:0] early_compare_left[1:5],early_compare_right[1:5];', 'wire [2:0] early_pair_result[0:5]; genvar compare_pair,compare_byte;', *bindings, comparator[0], 'assign wb_a_relation=early_pair_result[4]; assign wb_b_relation=early_pair_result[2];', 'always @(posedge clk or negedge rst_n) begin', 'if(!rst_n) wb_data<=0;', 'else if(mem_fire && !mem_fault) wb_data<=mem_value;', 'end'])
    return result.removesuffix('endmodule') + '\n'.join(extra) + '\nendmodule'


class WbByteRetimeTests(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix='wb-byte-retime-') as temporary:
            directory = Path(temporary)
            design = directory / 'design.sv'
            image = directory / 'test.vvp'
            design.write_text(wrapper(PARENT.read_text(), 'wb_byte_parent') + '\n' + wrapper(source, 'wb_byte_candidate'))
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'wb_byte_retime_tb', '-o', str(image), str(design), str(ROOT / 'sim/wb_byte_retime_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=120)

    def test_exact_source_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(), '5AF1F525BD65B1F0471F5F0CF765B28B1717D70C2885393BC4E2E87F5CA7515C')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        restored = CORE.read_text()
        for before, after in reversed(CHANGES):
            self.assertEqual(restored.count(after), 1)
            restored = restored.replace(after, before)
        self.assertEqual(restored, PARENT.read_text())

    def test_actual_capture_four_state_pair(self):
        result = self.simulate(CORE.read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS wb_byte_retime cycles=81920 resets=33', result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutants(self):
        source = CORE.read_text()
        variants = (
            ('reset_equality', "wb_a_byte_equal<=4'b1111;", "wb_a_byte_equal<=4'b0000;"),
            ('missing_refresh', 'if(ex_valid) begin compare_next_a=forwarded_a; compare_next_b=forwarded_b; end', "if(1'b0) begin compare_next_a=forwarded_a; compare_next_b=forwarded_b; end"),
            ('missing_id', 'if(id_fire) begin compare_next_a=id_operand_a; compare_next_b=id_operand_b; end', "if(1'b0) begin compare_next_a=id_operand_a; compare_next_b=id_operand_b; end"),
            ('lost_wb_hold', 'compare_next_wb=wb_data;', 'compare_next_wb=0;'),
            ('lost_operand_hold', 'compare_next_a=ex_operand_a;', 'compare_next_a=0;'),
            ('stale_wb', 'compare_next_wb=mem_value;', 'compare_next_wb=wb_data;'),
            ('fault_ignored', 'if(mem_fire && !mem_fault) compare_next_wb=mem_value;', 'if(mem_fire) compare_next_wb=mem_value;'),
            ('reversed_wb_a', 'compare_next_a[wb_compare_byte*8+:8]<compare_next_wb[wb_compare_byte*8+:8]', 'compare_next_wb[wb_compare_byte*8+:8]<compare_next_a[wb_compare_byte*8+:8]'),
            ('reversed_wb_b', 'compare_next_wb[wb_compare_byte*8+:8]<compare_next_b[wb_compare_byte*8+:8]', 'compare_next_b[wb_compare_byte*8+:8]<compare_next_wb[wb_compare_byte*8+:8]'),
            ('wrong_equal_operand', 'compare_next_a[wb_compare_byte*8+:8]==compare_next_wb[wb_compare_byte*8+:8]', 'compare_next_b[wb_compare_byte*8+:8]==compare_next_wb[wb_compare_byte*8+:8]'),
            ('wrong_pair_routing', 'assign byte_less=wb_a_byte_less;', 'assign byte_less=wb_b_byte_less;'),
        )
        for name, before, after in variants:
            self.assertEqual(source.count(before), 1)
            with self.subTest(name=name):
                result = self.simulate(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL wb_byte_retime', result.stdout)
                print('PASS WB byte runtime rejection: ' + name)
        before = '        if(ex_valid) begin compare_next_a=forwarded_a; compare_next_b=forwarded_b; end\n        if(id_fire) begin compare_next_a=id_operand_a; compare_next_b=id_operand_b; end'
        after = '\n'.join(reversed(before.splitlines()))
        self.assertEqual(source.count(before), 1)
        result = self.simulate(source.replace(before, after))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('FAIL wb_byte_retime', result.stdout)
        print('PASS WB byte runtime rejection: reversed_capture_priority')


if __name__ == '__main__':
    unittest.main(verbosity=2)
