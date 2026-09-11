from hashlib import sha256
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'experiments/wb_byte_retime/rv32_core.sv'
CORE=ROOT/'experiments/run_history_mem_nonzero/rv32_core.sv'


def wrapper(source,name):
    updates=re.findall(r'\bmem_rd<=([^;]+);',source)
    if updates!=['0','ex_rd']:
        raise ValueError('Unexpected actual MEM destination updates')
    if not re.search(r'if\(ex_fire\) begin\s+ex_valid<=0;[^\n]+\n[^\n]+\n[^\n]*mem_rd<=ex_rd;',source):
        raise ValueError('MEM destination update not in inspected EX fire scope')
    flags=re.findall(r'\bmem_rd_nonzero<=([^;]+);',source)
    if flags and len(flags)!=2:
        raise ValueError('Unexpected MEM nonzero updates')
    reset='mem_rd<=0;'+('mem_rd_nonzero<='+flags[0]+';' if flags else '')
    load='mem_rd<=ex_rd;'+('mem_rd_nonzero<='+flags[1]+';' if flags else '')
    return '\n'.join([
        'module '+name+'(input wire clk,rst_n,ex_fire,input wire [4:0] ex_rd,output reg [4:0] mem_rd,output wire nonzero);',
        'reg mem_rd_nonzero;' if flags else '',
        'assign nonzero='+('mem_rd_nonzero' if flags else 'mem_rd!=0')+';',
        'always @(posedge clk or negedge rst_n) begin',
        'if(!rst_n) begin '+reset+' end',
        'else if(ex_fire) begin '+load+' end',
        'end','endmodule'])


class MemRdNonzeroTests(unittest.TestCase):
    def simulate(self,source):
        with tempfile.TemporaryDirectory(prefix='mem-nonzero-') as temporary:
            directory=Path(temporary)
            design=directory/'design.sv'
            image=directory/'test.vvp'
            design.write_text(wrapper(PARENT.read_text(),'mem_rd_parent')+'\n'+wrapper(source,'mem_rd_candidate'))
            compile_result=subprocess.run(['iverilog','-g2012','-s','mem_rd_nonzero_tb','-o',str(image),str(design),str(ROOT/'sim/mem_rd_nonzero_tb.sv')],capture_output=True,text=True,timeout=30)
            self.assertEqual(compile_result.returncode,0,compile_result.stdout+compile_result.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=30)

    def test_exact_redundant_state_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'732509AD595EBC6EA0FD0B35F3D6ABA754D1D2169B27C3B5AF435BBFECCE0AC3')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'8F03BA996C5CE58CBA3F8499796B240B6B903946435EEDA48444FD158782E6A2')
        source=CORE.read_text()
        self.assertEqual(source.count('reg mem_rd_nonzero;'),1)
        self.assertEqual(source.count('mem_rd_nonzero'),8)
        self.assertEqual(source.count('mem_rd_nonzero<='),2)
        restored=source.replace('    reg mem_rd_nonzero;\n','').replace(' mem_rd_nonzero<=0;','').replace(' mem_rd_nonzero<=ex_rd!=0;','').replace('mem_rd_nonzero','mem_rd!=0')
        self.assertEqual(restored,PARENT.read_text())

    def test_actual_clocked_flag_equivalence(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS mem_rd_nonzero cycles=4096 resets=35 four_state_destinations=1024',result.stdout)
        print(result.stdout.strip())

    def test_actual_state_mutants_rejected(self):
        source=CORE.read_text()
        changes=(
            ('wrong_reset','mem_rd_nonzero<=0;','mem_rd_nonzero<=1;'),
            ('stale_destination','mem_rd_nonzero<=ex_rd!=0;','mem_rd_nonzero<=mem_rd!=0;'),
            ('lost_low_bit','mem_rd_nonzero<=ex_rd!=0;','mem_rd_nonzero<=ex_rd[4:1]!=0;'),
            ('only_low_bit','mem_rd_nonzero<=ex_rd!=0;','mem_rd_nonzero<=ex_rd[0]!=0;'),
        )
        for name,before,after in changes:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL mem_rd_nonzero',result.stdout)
                print('PASS mem nonzero state rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
