import re
from pathlib import Path
import unittest

from load_use_profile import file_hash
from loop_pending_address_native import inspect_address_chains,pins

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / 'build/loop-predictor-pending-pc-match-stage/build/pds/20260909-080806-ca492baf/synthesize/pds_soc_top_syn.vm'
NATIVE = ROOT / 'build/loop-predictor-pending-address-slice-stage/build/pds/20260909-082255-aa21f3d9/synthesize/pds_soc_top_syn.vm'


class AddressNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.actual = inspect_address_chains(cls.native,2,15)
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__))+' checker_sha256='+file_hash(ROOT / 'scripts/loop_pending_address_native.py'))

    def test_both_actual_chain_widths(self):
        self.assertEqual(file_hash(PARENT),'4966022F647F201C82280F54C508299EE218113023426778FA91BD026938FA4A')
        self.assertEqual(file_hash(NATIVE),'D23B9910343E3984E4428E8FD0666E361A818C477CCF9EE9F3B3DC0221AF3254')
        parent = inspect_address_chains(PARENT.read_text(),0,31)
        self.assertEqual(parent['truth_checks'],4224)
        self.assertEqual(self.actual['truth_checks'],1920)
        self.assertEqual(parent['pending_gate_sha256'],self.actual['pending_gate_sha256'])
        self.assertEqual([entry['stages'] for entry in parent['chains'].values()],[16,16])
        self.assertEqual([entry['stages'] for entry in self.actual['chains'].values()],[7,7])
        print('PASS native address chains parent_checks=4224 candidate_checks=1920 stages=16+16->7+7')

    def test_actual_gate_mutations_rejected(self):
        module = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',self.native)[0]
        blocks = re.findall(r'GTP_LUT6CARRY\b[^;]*;',module)
        changes = []
        for prefix,operation in (('N81','eq'),('N79','lt')):
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
        gate = next(block for block in blocks if pins(block).get('Z') == 'loop_pending_taken')
        changes.append(('gate_missing_invalidate',gate,gate.replace(pins(gate)['I0'],"1'b0")))
        changes.append(('gate_missing_training',gate,gate.replace('train_update_co',"1'b1")))
        for name,before,after in changes:
            self.assertEqual(self.native.count(before),1)
            self.assertNotEqual(before,after)
            with self.subTest(name=name),self.assertRaises(ValueError):
                inspect_address_chains(self.native.replace(before,after),2,15)
            print('PASS native address rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
