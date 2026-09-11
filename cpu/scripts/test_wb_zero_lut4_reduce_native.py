from pathlib import Path
import re
import unittest

from wb_zero_native import inspect_wb_byte_zero

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/timer-irq-next-stage/build/pds/20260909-011430-8304d6bb/synthesize/pds_soc_top_syn.vm'


class WbZeroLut4ReduceTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_wb_byte_zero(self.native)
        blocks=[block for block in re.findall(r'GTP_LUT4\b[^;]*;',self.native) if '.Z (early_data_zero[3])' in block]
        self.assertEqual(len(blocks),1)
        self.reducer=blocks[0]

    def test_actual_four_input_reduction(self):
        self.assertEqual(len(self.result['bytes']),4)
        truth=int(re.search(r'\.INIT\(16\x27b([01]+)\)',self.reducer)[1],2)
        for value in range(16):
            self.assertEqual((truth>>value)&1,int(value==15))
        self.assertGreater(self.result['consumers'],0)
        print('PASS native WB LUT4 reduction truth_inputs=16')

    def test_each_truth_bit_rejected(self):
        bits=re.search(r'\.INIT\(16\x27b([01]+)\)',self.reducer)[1]
        for index in range(16):
            mutated=bits[:index]+str(1-int(bits[index]))+bits[index+1:]
            with self.assertRaisesRegex(ValueError,'WB zero LUT4 final reduction changed'):
                inspect_wb_byte_zero(self.native.replace(self.reducer,self.reducer.replace(bits,mutated)))
            print('PASS WB LUT4 rejection: truth_'+str(index))

    def test_each_source_input_rejected(self):
        for index in range(4):
            before=f'.I{index} (early_wb_byte_zero[{index}])'
            self.assertIn(before,self.reducer)
            with self.assertRaisesRegex(ValueError,'WB zero final byte reduction changed'):
                inspect_wb_byte_zero(self.native.replace(self.reducer,self.reducer.replace(before,f'.I{index} (early_wb_byte_zero[{(index+1)%4}])')))
            print('PASS WB LUT4 rejection: source_'+str(index))

    def test_missing_duplicate_or_inactive_reduction(self):
        for name,changed in (
            ('missing',self.native.replace(self.reducer,'')),
            ('duplicate',self.native.replace(self.reducer,self.reducer+'\n'+self.reducer)),
            ('inactive',re.sub(r'(\.I[0-5]\s*\()early_data_zero\[3\]\s*\)',r"\g<1>1'b0)",self.native)),
        ):
            with self.assertRaises(ValueError):
                inspect_wb_byte_zero(changed)
            print('PASS WB LUT4 rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
