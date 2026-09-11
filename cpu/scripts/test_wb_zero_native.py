from pathlib import Path
import re
import unittest

from wb_zero_native import BYTE_INIT,inspect_wb_byte_zero

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/wb-zero-byte-reduce-stage/build/pds/20260908-202045-8396e28e/synthesize/pds_soc_top_syn.vm'


class WbZeroNativeTests(unittest.TestCase):
    def setUp(self):
        self.original=NATIVE.read_text()
        self.result=inspect_wb_byte_zero(self.original)
        self.assertEqual(len(self.result['bytes']),4)

    def test_actual_four_byte_cone(self):
        self.assertEqual([record['source_bits'] for record in self.result['bytes']],[list(range(index*8,index*8+8)) for index in range(4)])
        self.assertGreater(self.result['consumers'],0)

    def test_missing_each_boundary(self):
        for record in self.result['bytes']:
            with self.subTest(byte=record['byte']):
                with self.assertRaisesRegex(ValueError,'Missing unique WB zero driver'):
                    inspect_wb_byte_zero(self.original.replace(record['signal'],'removed_byte'))
                print('PASS WB native boundary rejection: '+record['signal'])

    def test_each_byte_source_mapping(self):
        for record in self.result['bytes']:
            bit=record['byte']*8+7
            before=f'.I3 (trace_data[{bit}])'
            blocks=[block for block in re.findall(r'GTP_LUT6CARRY\b[^;]*;',self.original) if '.COUT ('+record['carry']+')' in block]
            self.assertEqual(len(blocks),1)
            self.assertIn(before,blocks[0])
            altered=self.original.replace(blocks[0],blocks[0].replace(before,f'.I3 (trace_data[{(bit+8)%32}])'))
            with self.assertRaisesRegex(ValueError,'WB zero byte source bits changed'):
                inspect_wb_byte_zero(altered)
            print('PASS WB native source bit rejection: '+str(bit))

    def test_each_carry_connection(self):
        for record in self.result['bytes']:
            before='.CIN ('+record['carry']+')'
            self.assertEqual(self.original.count(before),1)
            with self.assertRaisesRegex(ValueError,'WB zero byte carry connection changed'):
                inspect_wb_byte_zero(self.original.replace(before,'.CIN ()'))
            print('PASS WB native carry rejection: '+record['signal'])

    def test_reduction_and_consumers(self):
        with self.assertRaisesRegex(ValueError,'WB zero final byte reduction changed'):
            inspect_wb_byte_zero(self.original.replace('.I0 (early_wb_byte_zero[0])',".I0 (1'b1)"))
        print('PASS WB native final reduction rejection')
        altered,count=re.subn(r'\.I[0-5]\s*\(early_data_zero\[3\]\s*\)',lambda match:match[0].replace('early_data_zero[3]',"1'b0"),self.original)
        self.assertGreater(count,0)
        with self.assertRaisesRegex(ValueError,'WB zero result has no active consumers'):
            inspect_wb_byte_zero(altered)
        print('PASS WB native consumer rejection')

    def test_configuration_rejections(self):
        record=self.result['bytes'][0]
        blocks=[block for block in re.findall(r'GTP_LUT6CARRY\b[^;]*;',self.original) if '.Z ('+record['signal']+')' in block]
        self.assertEqual(len(blocks),1)
        block=blocks[0]
        for before,after in ((BYTE_INIT,'1'+BYTE_INIT[1:]),('.I5_TO_CARRY("TRUE")','.I5_TO_CARRY("FALSE")'),('.I5_TO_LUT("FALSE")','.I5_TO_LUT("TRUE")')):
            self.assertIn(before,block)
            with self.assertRaisesRegex(ValueError,'WB zero native primitive configuration changed'):
                inspect_wb_byte_zero(self.original.replace(block,block.replace(before,after)))
            print('PASS WB native primitive configuration rejection')

    def test_ambiguous_cpu(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_wb_byte_zero(self.original+'\nmodule rv32_core; endmodule\n')
        print('PASS WB native ambiguous CPU rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
