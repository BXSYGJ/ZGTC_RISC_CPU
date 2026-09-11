from pathlib import Path
import re
import unittest

from relation_merge_native import inspect_merged_relations,inspect_relation_replication

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/branch-relation-merge-stage/build/pds/20260908-215230-3b3de172/synthesize/pds_soc_top_syn.vm'


class RelationMergeNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()

    def test_actual_merged_truth_tables(self):
        result=inspect_merged_relations(self.native)
        self.assertEqual(result['checks'],3072)
        self.assertEqual(len(result['pairs']),6)
        self.assertTrue(all(len(record['cone'])==2 for record in result['pairs']))

    def test_actual_replicated_selectors(self):
        result=inspect_relation_replication(self.native)
        self.assertEqual([record['consumers'] for record in result['a']],[7,17,16])
        self.assertEqual([record['consumers'] for record in result['b']],[24,17])

    def test_each_relation_boundary_truth_and_pin(self):
        for pair in range(6):
            signal=f'early_pair_condition[{pair}]'
            blocks=[block for block in re.findall(r'GTP_LUT6\b[^;]*;',self.native) if re.search(r'\.Z\s*\('+re.escape(signal)+r'\)',block)]
            self.assertEqual(len(blocks),1)
            block=blocks[0]
            with self.assertRaisesRegex(ValueError,'Missing unique merged relation driver'):
                inspect_merged_relations(self.native.replace(block,''))
            bits=re.search(r'\.INIT\(64\x27b([01]+)\)',block)[1]
            changed=bits[:-1]+str(1-int(bits[-1]))
            with self.assertRaisesRegex(ValueError,'truth-table mismatch'):
                inspect_merged_relations(self.native.replace(block,block.replace(bits,changed)))
            altered=block.replace('ex_instruction[13]','ex_instruction[12]')
            with self.assertRaisesRegex(ValueError,'merge is not direct or active'):
                inspect_merged_relations(self.native.replace(block,altered))
            print('PASS merged relation boundary/INIT/decode rejection: '+str(pair))

    def test_each_replica_is_required(self):
        records=inspect_relation_replication(self.native)
        for copies in records.values():
            for record in copies:
                blocks=[block for block in re.findall(r'GTP_LUT6\b[^;]*;',self.native) if re.search(r'\.Z\s*\('+re.escape(record['signal'])+r'\)',block)]
                self.assertEqual(len(blocks),1)
                with self.assertRaisesRegex(ValueError,'count or source mapping changed'):
                    inspect_relation_replication(self.native.replace(blocks[0],''))
                print('PASS relation inherited replica rejection: '+record['signal'])

    def test_duplicate_module_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_merged_relations(self.native+'\nmodule rv32_core; endmodule\n')


if __name__=='__main__':
    unittest.main(verbosity=2)
