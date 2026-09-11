from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from raw_pair_native import inspect_raw_pair_retime,native_comparison_design

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/raw-pair-retime-stage/build/pds/20260909-025726-1135e685/synthesize/pds_soc_top_syn.vm'


class RawPairNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=NATIVE.read_text()
        cls.report,cls.cells=inspect_raw_pair_retime(cls.native)
        core=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',cls.native)[0]
        cls.blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',core)

    def test_actual_predicate_mutations(self):
        block=next(block for block in self.blocks if re.search(r'\.Z5\s*\(early_pair_condition\[0\]\)',block))
        truth=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
        for name,changed in (('predicate_truth',block.replace(truth,truth[:-1]+str(1-int(truth[-1])))),('predicate_input',block.replace('.I3 (ex_instruction[13])','.I3 (ex_instruction[14])'))):
            with self.assertRaises(ValueError):
                inspect_raw_pair_retime(self.native.replace(block,changed))
            print('PASS raw native rejection: '+name)

    def test_actual_common_capture(self):
        self.assertEqual(len(self.report['capture_registers']),67)
        self.assertEqual(self.report['enable_truth_inputs'],32)
        print('PASS raw native capture registers=67 enable_truth=32 cells='+str(len(self.cells)))

    def test_capture_and_enable_mutations(self):
        for family,count in (('raw_pair_relation',3),('ex_operand_a',32),('ex_operand_b',32)):
            for bit in range(count):
                identifier=chr(92)+family+'['+str(bit)+']'
                matches=[block for block in self.blocks if block.startswith('GTP_DFF') and re.search(re.escape(identifier)+r'\s+\(',block)]
                self.assertEqual(len(matches),1)
                block=matches[0]
                self.assertEqual(block.count('.CE (N2242)'),1)
                with self.assertRaises(ValueError):
                    inspect_raw_pair_retime(self.native.replace(block,block.replace('.CE (N2242)','.CE (id_fire)')))
                print('PASS raw native rejection: capture_'+family+'_'+str(bit))
        block=next(block for block in self.blocks if re.search(r'\.Z\s*\(N2242\)',block))
        truth=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
        changed=str(1-int(truth[0]))+truth[1:]
        with self.assertRaises(ValueError):
            inspect_raw_pair_retime(self.native.replace(block,block.replace(truth,changed)))
        print('PASS raw native rejection: shared_enable_truth')

    def run_vendor(self,native):
        design=native_comparison_design(native)
        vendor=Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')
        kinds=sorted(set(re.findall(r'\b(GTP_[A-Z0-9_]+)\b',design)))
        models=[vendor/(name+'.v') for name in kinds]+[vendor/name for name in ('GTP_LUT5.v','GTP_MUX2LUT6.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v') if name[:-2] not in kinds]
        with tempfile.TemporaryDirectory(prefix='raw-native-') as temporary:
            directory=Path(temporary)
            source=directory/'native.sv'
            source.write_text(design)
            image=directory/'test.vvp'
            compiled=subprocess.run(['iverilog','-g2012','-s','raw_pair_native_tb','-o',str(image),str(source),str(ROOT/'sim/raw_pair_native_tb.sv'),*map(str,models)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=180)

    def test_actual_vendor_unsigned_equality(self):
        result=self.run_vendor(self.native)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS raw native unsigned equality checks=16384',result.stdout)
        print(result.stdout.strip())

    def test_vendor_rejects_wrong_data_selection(self):
        block=next(block for block in self.blocks if re.search(r'\.Z\s*\(N2247\[1\]\)',block))
        self.assertEqual(block.count(".INIT(8'b11001010)"),1)
        changed=self.native.replace(block,block.replace(".INIT(8'b11001010)",".INIT(8'b10101100)"))
        result=self.run_vendor(changed)
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('FAIL raw native relation',result.stdout)
        print('PASS raw native vendor rejection: wrong_selection')


if __name__=='__main__':
    unittest.main(verbosity=2)
