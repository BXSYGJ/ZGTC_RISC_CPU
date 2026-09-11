from pathlib import Path
import re
import unittest

from alu_group_native import inspect_arithmetic_group

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT / 'build/alu-arithmetic-group-stage/build/pds/20260908-204831-6bbec877/synthesize/pds_soc_top_syn.vm'


class ArithmeticGroupNativeTests(unittest.TestCase):
    def setUp(self):
        self.original=NATIVE.read_text()
        self.records=inspect_arithmetic_group(self.original)
        self.assertEqual(len(self.records),32)

    def block(self,signal):
        matches=re.findall(r'GTP_LUT3\b[^;]*\.Z\s*\('+re.escape(signal)+r'\s*\)[^;]*;',self.original)
        self.assertEqual(len(matches),1)
        return matches[0]

    def test_actual_thirty_two_muxes(self):
        self.assertEqual(len({record['signal'] for record in self.records}),32)
        self.assertTrue(all(record['consumers']>0 for record in self.records))

    def test_each_mux_is_required(self):
        for record in self.records:
            with self.subTest(signal=record['signal']):
                with self.assertRaisesRegex(ValueError,'Missing unique arithmetic group mux'):
                    inspect_arithmetic_group(self.original.replace(record['signal'],'removed_arithmetic_mux'))
                print('PASS arithmetic native boundary rejection: '+record['signal'])

    def test_each_word_endpoint_mapping(self):
        for suffix in ('zero','one'):
            for bit in (0,15):
                signal=f'arithmetic_high_{suffix}[{bit}]'
                block=self.block(signal)
                before=f'.I1 (difference_high_{suffix}[{bit}])'
                self.assertIn(before,block)
                altered=block.replace(before,f'.I1 (sum_high_{suffix}[{bit}])')
                with self.assertRaisesRegex(ValueError,'Arithmetic group mux inputs changed'):
                    inspect_arithmetic_group(self.original.replace(block,altered))
                print('PASS arithmetic native mapping rejection: '+signal)

    def test_control_and_init(self):
        for suffix in ('zero','one'):
            block=self.block(f'arithmetic_high_{suffix}[0]')
            for before,after,reason in (('.I0 (operation[0])','.I0 (operation[1])','Arithmetic group mux inputs changed'),('11011000','11011001','Arithmetic group mux INIT changed')):
                self.assertIn(before,block)
                with self.assertRaisesRegex(ValueError,reason):
                    inspect_arithmetic_group(self.original.replace(block,block.replace(before,after)))
                print('PASS arithmetic native control/INIT rejection: '+suffix)

    def test_consumer_is_required(self):
        signal='arithmetic_high_zero[0]'
        altered,count=re.subn(r'\.I[0-5]\s*\('+re.escape(signal)+r'\s*\)',lambda match:match[0].replace(signal,"1'b0"),self.original)
        self.assertGreater(count,0)
        with self.assertRaisesRegex(ValueError,'Arithmetic group mux lacks active consumers'):
            inspect_arithmetic_group(altered)
        print('PASS arithmetic native consumer rejection')

    def test_ambiguous_alu_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous native ALU module'):
            inspect_arithmetic_group(self.original+'\nmodule rv32_alu; endmodule\n')
        print('PASS arithmetic native ambiguous ALU rejection')


if __name__=='__main__':
    unittest.main(verbosity=2)
