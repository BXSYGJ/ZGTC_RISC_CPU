from hashlib import sha256
from pathlib import Path
import unittest

import test_wb_zero_byte_reduce as probes

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'experiments/forward_select_maxfan/rv32_core.sv'
CORE=ROOT/'experiments/branch_relation_merge/rv32_core.sv'
OLD="    (* syn_keep=1 *) wire [2:0] early_pair_result[0:5];"
NEW="    wire [2:0] early_pair_result[0:5];"


class BranchRelationMergeTests(unittest.TestCase):
    def simulate(self,source):
        return probes.LateBranchPredicateTests().run_probe(source)

    def test_exact_attribute_only_delta(self):
        self.assertEqual(sha256(PARENT.read_bytes()).hexdigest().upper(),'4A5BA5768E0FC87B43C349454A7CD176A4B0DE2B503C45931FAC1F35E3BB0D77')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(),'15B817A84D38F54F2A02ACC6A3E2B1EB20EB61200B39E05805FA31245458EFE6')
        source=CORE.read_text()
        self.assertEqual(source.count(NEW),1)
        self.assertEqual(source.replace(NEW,OLD),PARENT.read_text())
        self.assertEqual(source.count('syn_maxfan=24'),2)

    def test_actual_candidate_independent_branch_matrix(self):
        result=self.simulate(CORE.read_text())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS late_branch_predicate checks=589824 selectors=524288 random=65536 conditions=7077888',result.stdout)
        print(result.stdout.strip())

    def test_relevant_runtime_rejections(self):
        source=CORE.read_text()
        mutations=(
            ('wrong_pair_sign','? early_compare_left[compare_pair][31] : unsigned_less','? early_compare_right[compare_pair][31] : unsigned_less'),
            ('wrong_condition_decode',"ex_instruction[14:13]==2'b11,ex_instruction[14:13]==2'b10","ex_instruction[14:13]==2'b10,ex_instruction[14:13]==2'b11"),
            ('wrong_reverse_signed','!early_pair_result[5][2] && !early_pair_result[5][0]','!early_pair_result[5][2] && early_pair_result[5][0]'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.simulate(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL late_branch_predicate',result.stdout)
                print('PASS relation merge runtime rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
