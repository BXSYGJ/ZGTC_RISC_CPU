from pathlib import Path
import re
import unittest

from wb_zero_native import inspect_wb_byte_zero

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/branch-relation-merge-stage/build/pds/20260908-215230-3b3de172/synthesize/pds_soc_top_syn.vm'


class WbZeroLutMappingTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.records=inspect_wb_byte_zero(self.native)['bytes']
        self.blocks=re.findall(r'GTP_LUT(?:4|5)\b[^;]*;',self.native)

    def driver(self,signal):
        matched=[block for block in self.blocks if re.search(r'\.Z\s*\('+re.escape(signal)+r'\)',block)]
        self.assertEqual(len(matched),1)
        return matched[0]

    def test_actual_byte_truth_tables(self):
        self.assertEqual(len(self.records),4)
        for record in self.records:
            self.assertEqual(record['primitive_layout'],'LUT4_then_LUT5')
            lower=self.driver(record['signal'])
            upper=self.driver(record['carry'])
            lower_init=int(re.search(r'\.INIT\(32\x27b([01]+)\)',lower)[1],2)
            upper_init=int(re.search(r'\.INIT\(16\x27b([01]+)\)',upper)[1],2)
            for value in range(256):
                high=(upper_init>>(value>>4))&1
                actual=(lower_init>>((high<<4)|(value&15)))&1
                self.assertEqual(actual,int(value==0))
        print('PASS actual LUT byte zero 1024 truth-table inputs')

    def test_each_byte_mapping_and_connection_rejections(self):
        for record in self.records:
            lower=self.driver(record['signal'])
            upper=self.driver(record['carry'])
            for block in (lower,upper):
                altered=re.sub(r'\.I0 \(trace_data\[\d+\]\)',".I0 (1'b0)",block)
                self.assertNotEqual(altered,block)
                with self.assertRaisesRegex(ValueError,'source bits changed'):
                    inspect_wb_byte_zero(self.native.replace(block,altered))
            with self.assertRaisesRegex(ValueError,'Missing unique WB zero driver'):
                inspect_wb_byte_zero(self.native.replace(upper,''))
            print('PASS LUT byte low/high/missing connection rejection: '+record['signal'])

    def test_init_and_input_configuration_rejections(self):
        record=self.records[0]
        lower=self.driver(record['signal'])
        upper=self.driver(record['carry'])
        for block,width,reason in ((lower,32,'LUT5 configuration changed'),(upper,16,'LUT4 configuration changed')):
            altered=block.replace('.INIT('+str(width)+"'b0",'.INIT('+str(width)+"'b1")
            with self.assertRaisesRegex(ValueError,reason):
                inspect_wb_byte_zero(self.native.replace(block,altered))
        altered=lower.replace('.I4 (','.I5 (')
        with self.assertRaisesRegex(ValueError,'LUT5 configuration changed'):
            inspect_wb_byte_zero(self.native.replace(lower,altered))
        print('PASS LUT byte two INIT and wrong-port rejections')

    def test_mixed_lut_and_carry_mapping(self):
        path=ROOT/'build/alu-arithmetic-group-stage/build/pds/20260908-204831-6bbec877/synthesize/pds_soc_top_syn.vm'
        records=inspect_wb_byte_zero(path.read_text())['bytes']
        self.assertEqual([record['byte'] for record in records if record.get('primitive_layout')=='LUT4_then_LUT5'],[2,3])


if __name__=='__main__':
    unittest.main(verbosity=2)
