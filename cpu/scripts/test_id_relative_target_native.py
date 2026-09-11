from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from id_relative_target_native import inspect_id_relative_target,native_adder_design

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/id-relative-target-stage/build/pds/20260909-022522-f1351b42/synthesize/pds_soc_top_syn.vm'


class IdRelativeTargetNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=NATIVE.read_text()
        cls.result=inspect_id_relative_target(cls.native)
        core=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',cls.native)[0]
        cls.blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)

    def block(self,port,signal):
        matches=[block for block in self.blocks if re.search(r'\.'+port+r'\s*\('+re.escape(signal)+r'\s*\)',block)]
        self.assertEqual(len(matches),1)
        return matches[0]

    def test_actual_capture_boundary(self):
        self.assertEqual((self.result['target_registers'],self.result['pc_registers'],self.result['alias_registers'],self.result['carry_cells']),(32,32,15,32))
        print('PASS target native capture target=32 pc=32 aliases=15 carry=32')

    def reject(self,name,block,before,after):
        self.assertEqual(block.count(before),1)
        self.assertEqual(self.native.count(block),1)
        with self.assertRaises(ValueError):
            inspect_id_relative_target(self.native.replace(block,block.replace(before,after)))
        print('PASS target native rejection: '+name)

    def test_each_capture_data_and_enable(self):
        for bit in range(32):
            block=self.block('Q',f'early_target[{bit}]')
            self.reject('data_'+str(bit),block,f'.D (N1504[{bit}])',f'.D (N1504[{(bit+1)%32}])')
            self.reject('enable_'+str(bit),block,'.CE (id_fire)','.CE (ex_fire)')

    def test_reset_clock_pc_alias_and_carry(self):
        block=self.block('Q','early_target[0]')
        self.reject('reset',block,".INIT(1'b0)",".INIT(1'b1)")
        self.reject('clock',block,'.CLK (clk)','.CLK (id_fire)')
        block=self.block('Q','ex_pc[0]')
        self.reject('pc_capture',block,'.CE (id_fire)','.CE (ex_fire)')
        block=self.block('Q','id_rs1[0]')
        self.reject('instruction_alias',block,'.D (if_instruction[15])','.D (if_instruction[16])')
        block=self.block('Z','N1504[1]')
        before=re.search(r'\.CIN\s*\([^)]+\)',block)[0]
        self.reject('carry_chain',block,before,".CIN (1'b0)")
        self.reject('carry_mode',block,'.I5_TO_LUT("FALSE")','.I5_TO_LUT("TRUE")')

    def test_missing_and_duplicate_capture(self):
        block=self.block('Q','early_target[31]')
        for name,changed in (('missing',self.native.replace(block,'')),('duplicate',self.native.replace(block,block+'\n'+block))):
            with self.assertRaises(ValueError):
                inspect_id_relative_target(changed)
            print('PASS target native rejection: '+name)

    def run_vendor(self,native):
        design=native_adder_design(native)
        vendor=Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
        kinds=sorted(set(re.findall(r'\b(GTP_[A-Z0-9_]+)\b',design)))
        models=[vendor/(kind+'.v') for kind in kinds]+[vendor/name for name in ('GTP_MUX2LUT6.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v') if name[:-2] not in kinds]
        with tempfile.TemporaryDirectory(prefix='relative-target-native-') as temporary:
            directory=Path(temporary)
            source=directory/'native.sv'
            source.write_text(design)
            image=directory/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','id_relative_target_native_tb','-o',str(image),str(source),str(ROOT/'sim/id_relative_target_native_tb.sv'),str(ROOT/'build/id-relative-target-stage/rtl/rv32_decode.sv'),*map(str,models)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_actual_vendor_decoder_and_adder(self):
        result=self.run_vendor(self.native)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS relative native target checks=32768 branches=24576 jal=8192',result.stdout)
        print(result.stdout.strip())

    def test_vendor_rejects_wrong_adder_operand(self):
        block=self.block('Z','N1504[0]')
        self.assertEqual(block.count('.I0 (id_pc[0])'),1)
        result=self.run_vendor(self.native.replace(block,block.replace('.I0 (id_pc[0])','.I0 (id_pc[1])')))
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('FAIL relative native target',result.stdout)
        print('PASS target vendor runtime rejection: wrong_pc_bit')


if __name__=='__main__':
    unittest.main(verbosity=2)
