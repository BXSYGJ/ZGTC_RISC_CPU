import re
from pathlib import Path
import unittest

from load_use_profile import file_hash
from loop_address_single_native import inspect_single_bank
from loop_pending_address_native import pins

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/loop-predictor-address-single-bank-stage/build/pds/20260909-090931-424728c9/synthesize/pds_soc_top_syn.vm'


class AddressNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.actual = inspect_single_bank(cls.native)
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__))+' checker_sha256='+file_hash(ROOT / 'scripts/loop_address_single_native.py'))

    def test_actual_single_bank_mapping(self):
        self.assertEqual(file_hash(NATIVE),'DC3859D987C89AC31EAB060CDC1A815793A46274DD9AF6044E06005CCECB51EA')
        self.assertEqual(self.actual['truth_checks'],1864)
        self.assertEqual(self.actual['single_bank_register_bits'],30)
        self.assertEqual(self.actual['tag_bits'],14)
        self.assertEqual([entry['stages'] for entry in self.actual['chains'].values()],[7,7])
        print('PASS native single-bank address checks=1864 registers=30 tag_bits=14 stages=7+7')

    def test_actual_gate_mutations_rejected(self):
        module = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',self.native)[0]
        blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
        changes = []
        for prefix,operation in (('N75','eq'),('N73','lt')):
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
        for name,output,port in (('direction_invalidate','_N4474','I0'),('direction_training','_N4474','I2'),('admission_bank','N1677','I2')):
            gate = next(cell for cell in cells if pins(cell).get('Z') == output)
            changes.append((name,gate,gate.replace(pins(gate)[port],"1'b0")))
        direction = next(cell for cell in cells if pins(cell).get('Z') == '_N4474')
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
