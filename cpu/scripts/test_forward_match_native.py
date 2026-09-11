from pathlib import Path
import re
import unittest

from forward_match_native import inspect_forward_match

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/forward-match-retime-stage/build/pds/20260909-004247-5480b202/synthesize/pds_soc_top_syn.vm'


class ForwardMatchNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_forward_match(self.native)
        self.blocks=re.findall(r'GTP_[A-Z0-9_]+\b[^;]*;',self.native)

    def block(self,port,signal):
        matches=[block for block in self.blocks if re.search(r'\.'+port+r'\s*\('+re.escape(signal)+r'\s*\)',block)]
        self.assertEqual(len(matches),1)
        return matches[0]

    def reject(self,name,block,before,after):
        self.assertEqual(block.count(before),1)
        self.assertEqual(self.native.count(block),1)
        with self.assertRaises(ValueError):
            inspect_forward_match(self.native.replace(block,block.replace(before,after)))
        print('PASS native match rejection: '+name)

    def test_actual_precompute_mapping(self):
        self.assertEqual(self.result['truth_inputs'],6288)
        self.assertEqual(len(self.result['pipeline_registers_sha256']),20)
        self.assertEqual([self.result['match'][suffix]['consumers'] for suffix in ('a','b')],[6,4])
        print('PASS native match truth_inputs=6288 pipeline_registers=20 flags=2')

    def test_flag_capture_controls(self):
        for suffix in ('a','b'):
            block=self.block('Q','mem_match_'+suffix)
            for name,before,after in (
                ('clock','.CLK (clk)','.CLK (wrong_clock)'),
                ('enable','.CE ('+self.result['enable']+')',".CE (1'b1)"),
                ('reset',".INIT(1'b1)",".INIT(1'b0)"),
                ('grs','.GRS_EN("TRUE")','.GRS_EN("FALSE")'),
                ('preset','.P ('+self.result['reset']+' )',".P (1'b0)"),
            ):
                with self.subTest(suffix=suffix,name=name):
                    self.reject(suffix+'_'+name,block,before,after)

    def test_transfer_truth_tables(self):
        signals=[self.result['enable']]+[self.result['match'][suffix]['data'] for suffix in ('a','b')]
        for signal in signals:
            block=self.block('Z',signal)
            bits=re.search(r'\.INIT\(\d+\x27b([01]+)\)',block)[1]
            self.reject('truth_'+signal,block,bits,bits[:-1]+str(1-int(bits[-1])))
        block=self.block('Z',signals[0])
        self.reject('interrupt_enable',block,'.I3 (interrupt_pending)',".I3 (1'b0)")
        for signal in signals[1:]:
            block=self.block('Z',signal)
            self.reject('transfer_select_'+signal,block,'.I2 (ex_fire)','.I2 (id_fire)')

    def test_each_equality_gate_truth(self):
        for suffix in ('a','b'):
            for comparison in self.result['match'][suffix]['comparisons']:
                for signal in comparison['gate_sha256']:
                    block=self.block('Z',signal)
                    bits=re.search(r'\.INIT\(\d+\x27b([01]+)\)',block)[1]
                    self.reject('equality_'+signal,block,bits,bits[:-1]+str(1-int(bits[-1])))

    def test_pipeline_source_capture(self):
        for signal,port,after in (
            ('ex_instruction[7]','D','id_rd[1]'),
            ('ex_instruction[15]','D','id_rs2[0]'),
            ('ex_instruction[20]','D','id_rs1[0]'),
            ('mem_instruction[7]','D','ex_instruction[8]'),
            ('mem_instruction[7]','CE','id_fire'),
        ):
            block=self.block('Q',signal)
            before=re.search(r'\.'+port+r'\s*\([^)]+\)',block)[0]
            self.reject('pipeline_'+signal+'_'+port,block,before,'.'+port+' ('+after+')')

    def test_missing_duplicate_or_unused_state(self):
        block=self.block('Q','mem_match_a')
        for name,changed in (
            ('missing_flag',self.native.replace(block,'')),
            ('duplicate_flag',self.native.replace(block,block+'\n'+block)),
            ('duplicate_cpu',self.native+'\nmodule rv32_core; endmodule\n'),
            ('unused_flag',re.sub(r'(\.I[0-5]\s*\()mem_match_b\)',r"\g<1>1'b0)",self.native)),
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    inspect_forward_match(changed)
                print('PASS native match rejection: '+name)


if __name__=='__main__':
    unittest.main(verbosity=2)
