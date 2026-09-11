from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_forward_select_maxfan import wrapper as original_wrapper

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'experiments/wb_byte_retime/rv32_core.sv'
CORE = ROOT / 'experiments/loop_pending_wb_zero_elide/rv32_core.sv'


def wrapper(source, name):
    generated = original_wrapper(source, name)
    anchor = 'wire decode_t ex_decode={controls[5],controls[7]};'
    if generated.count(anchor) != 1:
        raise ValueError('Forwarding wrapper decode interface changed')
    return generated.replace(anchor, anchor + chr(10) + 'wire mem_match_a=ex_rs1==mem_rd,mem_match_b=ex_rs2==mem_rd;')


class WbZeroElisionTests(unittest.TestCase):
    def simulate(self, source):
        with tempfile.TemporaryDirectory(prefix='wb-zero-elision-') as temporary:
            directory = Path(temporary)
            design = directory / 'design.sv'
            image = directory / 'test.vvp'
            design.write_text(wrapper(PARENT.read_text(), 'forward_parent') + chr(10) + wrapper(source, 'forward_candidate'))
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'loop_pending_wb_zero_elide_tb', '-o', str(image), str(design), str(ROOT / 'sim/loop_pending_wb_zero_elide_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=180)

    def test_exact_single_condition_elision(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(), '732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), 'E0BDF217BFC7C604300862C1D759AE7338495F5CDCCAB7F01874728842558EF9')
        source = CORE.read_text()
        before = '        if(wb_valid && wb_writes && wb_rd!=0) begin'
        after = '        if(wb_valid && wb_writes) begin'
        self.assertEqual(source.count(after), 1)
        self.assertEqual(source.replace(after, before), PARENT.read_text())
        self.assertEqual(source.count('wb_rd!=0'), 1)
        self.assertIn('assign trace_write=wb_valid && wb_writes && wb_rd!=0;', source)
        self.assertNotIn('wb_rd_nonzero', source)

    def test_four_state_forwarding_equivalence(self):
        result = self.simulate(CORE.read_text())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS forward_select checks=2265152', result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutants_rejected(self):
        changes = (
            ('missing_write_permission', 'if(wb_valid && wb_writes) begin', 'if(wb_valid) begin'),
            ('missing_valid', 'if(wb_valid && wb_writes) begin', 'if(wb_writes) begin'),
            ('lost_zero_a', 'if(ex_rs1==0 || !ex_decode.uses_rs1) forwarded_a=0;', 'if(!ex_decode.uses_rs1) forwarded_a=0;'),
            ('lost_zero_b', 'if(ex_rs2==0 || !ex_decode.uses_rs2) forwarded_b=0;', 'if(!ex_decode.uses_rs2) forwarded_b=0;'),
            ('wrong_wb_match_b', 'if(ex_rs2==wb_rd) forwarded_b=wb_data;', 'if(ex_rs1==wb_rd) forwarded_b=wb_data;'),
            ('lost_mem_priority', 'if(mem_match_b) forwarded_b=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;', 'if(mem_match_b) forwarded_b=wb_data;'),
            ('wrong_load_bubble', 'if(mem_match_a) forwarded_a=LOAD_USE_BUBBLE!=0 ? mem_result : mem_value;', 'if(mem_match_a) forwarded_a=mem_value;'),
        )
        source = CORE.read_text()
        for name, before, after in changes:
            with self.subTest(name=name):
                self.assertEqual(source.count(before), 1)
                result = self.simulate(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL forward_select', result.stdout + result.stderr)
                print('PASS WB zero-elision runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
