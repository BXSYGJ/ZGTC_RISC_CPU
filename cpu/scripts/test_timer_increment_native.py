from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from timer_increment_native import inspect_timer_increment
from timer_next_native import inspect_timer_next
import test_timer_next_native as parent_native_tests

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/timer-increment-boundary-stage/build/pds/20260909-014133-12495d99/synthesize/pds_soc_top_syn.vm'


class TimerIncrementNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_timer_next(self.native,retained_increment=True)
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
            inspect_timer_next(self.native.replace(block,block.replace(before,after)),retained_increment=True)
        print('PASS increment native rejection: '+name)

    def test_actual_increment_and_capture(self):
        self.assertEqual(self.result['increment_boundary']['outputs'],64)
        self.assertEqual(self.result['increment_boundary']['truth_inputs'],4032)
        self.assertEqual(self.result['comparison_truth_inputs'],3080)
        self.assertEqual(self.result['capture_truth_inputs'],3072)
        self.assertEqual(self.result['increment_enable_complement_truth_inputs'],32)
        self.assertEqual(len(self.result['state_registers']),128)
        print('PASS retained increment truth=4032 comparison=3080 capture=3072 enable=32')

    def test_each_increment_cell_truth(self):
        for bit in range(64):
            block=self.block('Z',f'timer_incremented[{bit}]')
            bits=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
            changed=(str(1-int(bits[0]))+bits[1:]) if bit==0 else (bits[:-1]+str(1-int(bits[-1])))
            self.reject('truth_'+str(bit),block,bits,changed)

    def test_increment_control_isolation(self):
        for bit,port,after in ((0,'I5',"1'b0"),(1,'I0','req_data[0]'),(2,'CIN',"1'b0"),(63,'I0','req_data[31]')):
            block=self.block('Z',f'timer_incremented[{bit}]')
            before=re.search(r'\.'+port+r'\s*\([^)]+\)',block)[0]
            self.reject('isolation_'+str(bit),block,before,'.'+port+' ('+after+')')
        block=self.block('Z','timer_incremented[1]')
        self.reject('seed_mode',block,'.I5_TO_LUT("TRUE")','.I5_TO_LUT("FALSE")')

    def test_capture_and_complement_are_required(self):
        for signal,port,after in (('timer_value[32]','D','timer_value_next[33]'),('timer_compare[0]','CE','_N4205_inv'),('irq_timer','D','timer_upper_greater')):
            block=self.block('Q',signal)
            before=re.search(r'\.'+port+r'\s*\([^)]+\)',block)[0]
            self.reject(signal+'_'+port,block,before,'.'+port+' ('+after+')')
        block=self.block('Z','_N4197_inv')
        bits=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
        self.reject('enable_complement_truth',block,bits,str(1-int(bits[0]))+bits[1:])
        self.reject('enable_complement_input',block,'.I1 (req_address[2])','.I1 (req_address[3])')
        block=self.block('Q','timer_value[0]')
        self.reject('counter_reset',block,".INIT(1'b0)",".INIT(1'b1)")

    def test_actual_vendor_increment_cone(self):
        selected=[self.block('Z',f'timer_incremented[{bit}]') for bit in range(64)]
        self.assertEqual(len(set(selected)),64)
        nets={}
        for block in selected:
            for signal in re.findall(r'\.(?:Z|Z5|COUT|CIN|I[0-5])\s*\(([^)]*)\)',block):
                signal=signal.strip()
                if not signal or signal in ("1'b0","1'b1"):
                    continue
                match=re.fullmatch(r'(\w+)(?:\[(\d+)\])?',signal)
                self.assertIsNotNone(match,signal)
                name=match[1]
                if name in ('timer_value','timer_incremented'):
                    continue
                size=int(match[2]) if match[2] is not None else -1
                nets[name]=max(nets.get(name,-1),size)
        declarations='\n'.join(('wire '+name+';' if size<0 else f'wire [{size}:0] {name};') for name,size in sorted(nets.items()))
        wrapper='module timer_native_increment(input wire [63:0] timer_value,output wire [63:0] timer_incremented);\n'+declarations+'\n'+'\n'.join(selected)+'\nendmodule\n'
        vendor=Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
        models=[vendor/name for name in ('GTP_LUT6CARRY.v','GTP_LUT6D.v','GTP_LUT5.v','GTP_MUX2LUT6.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v')]
        with tempfile.TemporaryDirectory(prefix='timer-increment-native-') as temporary:
            directory=Path(temporary)
            source=directory/'native.sv'
            source.write_text(wrapper)
            image=directory/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','timer_increment_native_tb','-o',str(image),str(source),str(ROOT/'sim/timer_increment_native_tb.sv'),*map(str,models)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            result=subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('PASS timer native increment checks=4288',result.stdout)
            print(result.stdout.strip())

    def test_actual_vendor_comparison_cone(self):
        parent_native_tests.TimerNextNativeTests.test_actual_vendor_comparison_cone(self)

    def test_missing_or_duplicate_increment(self):
        block=self.block('Z','timer_incremented[1]')
        for name,changed in (('missing',self.native.replace(block,'')),('duplicate',self.native.replace(block,block+'\n'+block))):
            with self.assertRaises(ValueError):
                inspect_timer_increment(changed)
            print('PASS increment native rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
