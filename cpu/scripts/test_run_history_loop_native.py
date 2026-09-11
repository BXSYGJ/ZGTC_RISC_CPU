import re
from pathlib import Path
import unittest

from load_use_profile import file_hash
from run_history_loop_native import inspect_single_bank
from loop_pending_address_native import pins

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/run-history-loop-single-stage/build/pds/20260909-105029-08acf5ba/synthesize/pds_soc_top_syn.vm'


class AddressNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.actual = inspect_single_bank(cls.native)
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__))+' checker_sha256='+file_hash(ROOT / 'scripts/run_history_loop_native.py'))

    def test_actual_single_bank_mapping(self):
        self.assertEqual(file_hash(NATIVE),'CC41798D71C86FECBB57B09BDA270FA262B1D63558275B356C134B680CA42D2A')
        self.assertEqual(self.actual['truth_checks'],1864)
        self.assertEqual(self.actual['single_bank_register_bits'],30)
        self.assertEqual(self.actual['tag_bits'],14)
        self.assertEqual([entry['stages'] for entry in self.actual['chains'].values()],[7,7])
        print('PASS native single-bank address checks=1864 registers=30 tag_bits=14 stages=7+7')

    def test_actual_gate_mutations_rejected(self):
        module = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',self.native)[0]
        blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
        changes = []
        for prefix,operation in (('N87','eq'),('N85','lt')):
            for index in (0,3,6):
                matches = [block for block in blocks if re.search(re.escape(chr(92)+prefix+'.'+operation+'_'+str(index))+r'\s',block)]
                self.assertEqual(len(matches),1)
                block = matches[0]
                inverted = re.sub(r"(\.INIT\(64'b)([01]{64})",lambda found:found[1]+''.join('0' if bit=='1' else '1' for bit in found[2]),block)
                changes.append((f'truth_{operation}{index}',block,inverted))
                if index == 3:
                    changes.append(('wire_'+operation,block,block.replace(pins(block)['I0'],'wrong_address_bit')))
                    changes.append(('mode_'+operation,block,block.replace('.I5_TO_LUT("FALSE")','.I5_TO_LUT("TRUE")')))
                    changes.append(('duplicate_'+operation,block,block+chr(10)+block))
        cells = re.findall(r'GTP_\w+\b[^;]*;',module)
        for name,output,port in (('direction_invalidate','_N4481','I0'),('direction_training','_N4481','I2'),('admission_bank','N1683','I2')):
            gate = next(cell for cell in cells if pins(cell).get('Z') == output)
            changes.append((name,gate,gate.replace(pins(gate)[port],"1'b0")))
        direction = next(cell for cell in cells if pins(cell).get('Z') == '_N4481')
        changes.append(('direction_truth',direction,re.sub(r"(\.INIT\(64'b)([01]{64})",lambda found:found[1]+''.join('0' if bit=='1' else '1' for bit in found[2]),direction)))
        tag = next(cell for cell in cells if cell.startswith('GTP_DFF') and re.search(r'\.Q\s*\('+re.escape(chr(92))+r'loop_tags\[0\] \[0\]',cell))
        changes.append(('tag_data',tag,tag.replace('update_pc[2]','update_pc[3]')))
        changes.append(('second_slot',tag,tag.replace('loop_tags[0]','loop_tags[1]')))
        changes.append(('duplicate_register',tag,tag+chr(10)+tag))
        for name,before,after in changes:
            self.assertEqual(self.native.count(before),1)
            self.assertNotEqual(before,after)
            with self.subTest(name=name),self.assertRaises(ValueError):
                inspect_single_bank(self.native.replace(before,after))
            print('PASS native address rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
