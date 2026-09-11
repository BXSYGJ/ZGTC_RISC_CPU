from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
CORE = ROOT / 'experiments/loop_pending_wb_nonzero/rv32_core.sv'


def wrapper(source, name):
    updates = re.findall(r'\bwb_rd<=([^;]+);', source)
    if updates != ['0', 'mem_rd']:
        raise ValueError('Unexpected actual WB destination updates')
    matches = re.findall(r'if\(([^()]+)\) begin\s+(wb_pc<=mem_pc;[^\n]*)\n\s*end', source)
    if len(matches) != 1 or 'wb_rd<=mem_rd;' not in matches[0][1]:
        raise ValueError('Cannot locate unique actual WB capture block')
    trigger, capture = matches[0]
    flags = re.findall(r'\bwb_rd_nonzero<=([^;]+);', source)
    if flags and (len(flags) != 2 or ('wb_rd_nonzero<=' + flags[1] + ';') not in capture):
        raise ValueError('WB qualification update escaped its captured destination block')
    reset = 'wb_rd<=0;' + ('wb_rd_nonzero<=' + flags[0] + ';' if flags else '')
    if flags and reset not in source.replace(' ', ''):
        raise ValueError('WB destination and flag reset locations differ')
    load = 'wb_rd<=mem_rd;' + ('wb_rd_nonzero<=' + flags[1] + ';' if flags else '')
    return chr(10).join([
        'module ' + name + '(input wire clk,rst_n,mem_fire,mem_fault,input wire [4:0] mem_rd,output reg [4:0] wb_rd,output wire nonzero);',
        'reg wb_rd_nonzero;' if flags else '',
        'assign nonzero=' + ('wb_rd_nonzero' if flags else 'wb_rd!=0') + ';',
        'always @(posedge clk or negedge rst_n) begin',
        'if(!rst_n) begin ' + reset + ' end',
        'else if(' + trigger + ') begin ' + load + ' end',
        'end', 'endmodule'])


class WbDestinationNonzeroTests(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix='wb-destination-nonzero-') as temporary:
            directory = Path(temporary)
            design = directory / 'design.sv'
            image = directory / 'test.vvp'
            design.write_text(wrapper(PARENT.read_text(), 'wb_rd_parent') + chr(10) + wrapper(source, 'wb_rd_candidate'))
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'wb_rd_nonzero_tb', '-o', str(image), str(design), str(ROOT / 'sim/wb_rd_nonzero_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=30)

    def test_exact_redundant_state_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(), '732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '07236E586512B2A8E833B530A4212BF3AFD9D622A8E19E2FE469EC2113556238')
        source = CORE.read_text()
        self.assertEqual(source.count('reg wb_rd_nonzero;'), 1)
        self.assertEqual(source.count('wb_rd_nonzero'), 5)
        self.assertEqual(source.count('wb_rd_nonzero<='), 2)
        restored = source.replace('    reg wb_rd_nonzero;'+chr(10), '').replace(' wb_rd_nonzero<=0;', '').replace(' wb_rd_nonzero<=mem_rd!=0;', '').replace('wb_rd_nonzero', 'wb_rd!=0')
        self.assertEqual(restored, PARENT.read_text())
        self.assertIn('else if(mem_fire && !mem_fault)', wrapper(source, 'probe'))

    def test_actual_four_state_capture_equivalence(self):
        result = self.simulate(CORE.read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS wb_rd_nonzero cycles=17408 resets=35 four_state_destinations=1024 four_state_controls=16', result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutants_rejected(self):
        source = CORE.read_text()
        changes = (
            ('wrong_reset', 'wb_rd_nonzero<=0;', 'wb_rd_nonzero<=1;'),
            ('stale_destination', 'wb_rd_nonzero<=mem_rd!=0;', 'wb_rd_nonzero<=wb_rd!=0;'),
            ('lost_low_bit', 'wb_rd_nonzero<=mem_rd!=0;', 'wb_rd_nonzero<=mem_rd[4:1]!=0;'),
            ('only_low_bit', 'wb_rd_nonzero<=mem_rd!=0;', 'wb_rd_nonzero<=mem_rd[0]!=0;'),
            ('dropped_fault_gate', 'if(mem_fire && !mem_fault) begin'+chr(10)+'                wb_pc', 'if(mem_fire) begin'+chr(10)+'                wb_pc'),
            ('inverted_fault_gate', 'if(mem_fire && !mem_fault) begin'+chr(10)+'                wb_pc', 'if(mem_fire && mem_fault) begin'+chr(10)+'                wb_pc'),
            ('unconditional_capture', 'if(mem_fire && !mem_fault) begin'+chr(10)+'                wb_pc', "if(1'b1) begin"+chr(10)+'                wb_pc'),
        )
        for name, before, after in changes:
            with self.subTest(name=name):
                self.assertEqual(source.count(before), 1)
                result = self.simulate(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL wb_rd_nonzero', result.stdout + result.stderr)
                print('PASS WB destination nonzero runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
