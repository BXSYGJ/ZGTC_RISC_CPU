import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from timer_next_native import inspect_timer_next

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/timer-irq-next-stage/build/pds/20260909-011430-8304d6bb/synthesize/pds_soc_top_syn.vm'


class TimerNextNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_timer_next(self.native)
        module=re.findall(r'\bmodule\s+rv32_peripherals\b[\s\S]*?\bendmodule\b',self.native)[0]
        self.blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',module)

    def block(self,port,signal):
        matches=[block for block in self.blocks if re.search(r'\.'+port+r'\s*\('+re.escape(signal)+r'\s*\)',block)]
        self.assertEqual(len(matches),1)
        return matches[0]

    def reject(self,name,block,before,after):
        self.assertEqual(block.count(before),1)
        self.assertEqual(self.native.count(block),1)
        with self.assertRaises(ValueError):
            inspect_timer_next(self.native.replace(block,block.replace(before,after)))
        print('PASS timer native rejection: '+name)

    def test_actual_vendor_comparison_cone(self):
        hashes={cell['sha256'] for chain in self.result['comparison'].values() for cell in chain['cells']}
        hashes.add(self.result['reducer_sha256'])
        selected=[block for block in self.blocks if hashlib.sha256(block.encode()).hexdigest().upper() in hashes]
        self.assertEqual(len(selected),49)
        text='\n'.join(selected)
        buses=sorted(set(re.findall(r'(\\[^\s]+)\s+\[\d+\]',text)))
        self.assertEqual(len(buses),3)
        declarations='\n'.join('wire [32:0] '+bus+' ;' for bus in buses)
        wrapper='module timer_native_comparison(input wire [63:0] timer_value_next,timer_compare_next,output wire timer_interrupt_next);\nwire timer_upper_equal,timer_upper_greater,timer_lower_at_least;\n'+declarations+'\n'+text+'\nendmodule\n'
        vendor=Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
        models=[vendor/name for name in ('GTP_LUT6CARRY.v','GTP_LUT5.v','GTP_LUT3.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v')]
        with tempfile.TemporaryDirectory(prefix='timer-next-native-') as temporary:
            directory=Path(temporary)
            design=directory/'native.sv'
            design.write_text(wrapper)
            image=directory/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','timer_next_native_tb','-o',str(image),str(design),str(ROOT/'sim/timer_next_native_tb.sv'),*map(str,models)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            result=subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS timer_next_native checks=40256',result.stdout)
            print(result.stdout.strip())
            for model in models:
                print('PASS timer vendor model '+model.name+' sha256='+hashlib.sha256(model.read_bytes()).hexdigest().upper())

    def test_actual_registered_next_state_mapping(self):
        self.assertEqual(self.result['comparison_truth_inputs'],3080)
        self.assertEqual(self.result['capture_truth_inputs'],1304)
        self.assertEqual(len(self.result['state_registers']),128)
        self.assertEqual(sum(record['direct_next_capture'] for record in self.result['state_registers']),32)
        print('PASS timer native comparison=3080 capture=1304 state_registers=128 direct_capture=32')

    def test_irq_register_and_reducer(self):
        block=self.block('Q','irq_timer')
        for name,before,after in (
            ('clock','.CLK (clk)','.CLK (other_clock)'),
            ('reset',".INIT(1'b0)",".INIT(1'b1)"),
            ('clear','.C ('+self.result['reset']+' )',".C (1'b0)"),
            ('grs','.GRS_EN("TRUE")','.GRS_EN("FALSE")'),
            ('data','.D (timer_interrupt_next)','.D (timer_upper_greater)'),
        ):
            self.reject('irq_'+name,block,before,after)
        reducer=self.block('Z','timer_interrupt_next')
        self.reject('reducer_truth',reducer,".INIT(8'b11111000)",".INIT(8'b11110000)")
        self.reject('reducer_input',reducer,'.I1 (timer_upper_equal)','.I1 (timer_upper_greater)')

    def test_each_carry_cell_truth(self):
        for name,chain in self.result['comparison'].items():
            for cell in chain['cells']:
                block=self.block('COUT',cell['signal'])
                self.assertEqual(hashlib.sha256(block.encode()).hexdigest().upper(),cell['sha256'])
                bits=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
                self.reject(name+'_'+str(cell['pair']),block,bits,bits[:-1]+str(1-int(bits[-1])))

    def test_chain_connections_and_next_inputs(self):
        for name,chain in self.result['comparison'].items():
            last=self.block('COUT',chain['cells'][0]['signal'])
            first=self.block('COUT',chain['cells'][-1]['signal'])
            pin=re.search(r'\.I0\s*\(([^)]+)\)',last)[0]
            self.reject(name+'_next_source',last,pin,pin.replace('_next',''))
            self.reject(name+'_mode',last,'.I5_TO_CARRY("FALSE")','.I5_TO_CARRY("TRUE")')
            self.reject(name+'_seed',first,'.CIN ()',".CIN (1'b0)")

    def test_register_capture_correspondence(self):
        for signal,port,replacement in (
            ('timer_value[0]','CE','_N4202_inv'),
            ('timer_value[32]','D','timer_value_next[33]'),
            ('timer_compare[0]','CE','_N4205_inv'),
            ('timer_compare[32]','D','N72[1]'),
            ('timer_compare[63]','CLK','other_clock'),
        ):
            block=self.block('Q',signal)
            before=re.search(r'\.'+port+r'\s*\([^)]+\)',block)[0]
            self.reject(signal+'_'+port,block,before,'.'+port+' ('+replacement+')')
        block=self.block('Q','timer_compare[1]')
        self.reject('compare_reset',block,".INIT(1'b1)",".INIT(1'b0)")
        for signal,port,first_bit in (('N67[0]','Z',True),('_N12880','Z5',False)):
            block=self.block(port,signal)
            bits=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
            replacement=(str(1-int(bits[0]))+bits[1:]) if first_bit else (bits[:-1]+str(1-int(bits[-1])))
            self.reject(signal+'_capture_truth',block,bits,replacement)

    def test_missing_duplicate_registers(self):
        block=self.block('Q','irq_timer')
        for name,changed in (
            ('missing_irq',self.native.replace(block,'')),
            ('duplicate_irq',self.native.replace(block,block+'\n'+block)),
            ('duplicate_peripheral',self.native+'\nmodule rv32_peripherals; endmodule\n'),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    inspect_timer_next(changed)
                print('PASS timer native rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
