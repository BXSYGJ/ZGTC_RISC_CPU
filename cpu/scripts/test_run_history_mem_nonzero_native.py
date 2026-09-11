from pathlib import Path
import re
import unittest

from mem_nonzero_native import inspect_mem_nonzero_register
from load_use_profile import file_hash

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'build/run-history-mem-nonzero-stage/build/pds/20260909-100917-7cf78cf3/synthesize/pds_soc_top_syn.vm'


class MemNonzeroNativeTests(unittest.TestCase):
    def setUp(self):
        self.native=NATIVE.read_text()
        self.result=inspect_mem_nonzero_register(self.native)
        self.register=next(block for block in re.findall(r'GTP_DFF_CE\b[^;]*;',self.native) if '.Q (mem_rd_nonzero)' in block)
        self.precompute=next(block for block in re.findall(r'GTP_LUT5\b[^;]*;',self.native) if '.Z ('+self.result['input']+')' in block)

    def test_actual_registered_precompute(self):
        self.assertEqual(file_hash(NATIVE),'CA8B1E9D4A4098C6D8AA5A31BE5DA1FC198280FD426E5A5B9A680956A20D82CB')
        self.assertEqual(file_hash(ROOT/'scripts/mem_nonzero_native.py'),'A49D4D97E37AA3A3089329E3D5CB4F8E2991E85D2B3A0634C15A436ECA539057')
        print('BOUND native_sha256='+file_hash(NATIVE)+' test_sha256='+file_hash(Path(__file__))+' helper_sha256='+file_hash(ROOT/'scripts/mem_nonzero_native.py'))
        self.assertEqual(self.result['truth_inputs'],32)
        self.assertEqual(self.result['consumers'],5)
        self.assertEqual(len(self.result['destination_registers_sha256']),5)

    def test_flag_capture_controls(self):
        for before,after in (('.CE (ex_fire)',".CE (1'b1)"),('.CLK (clk)','.CLK (wrong_clock)'),(".INIT(1'b0)",".INIT(1'b1)"),('.GRS_EN("TRUE")','.GRS_EN("FALSE")')):
            with self.subTest(before=before):
                self.assertIn(before,self.register)
                with self.assertRaises(ValueError):
                    inspect_mem_nonzero_register(self.native.replace(self.register,self.register.replace(before,after)))
                print('PASS MEM flag capture rejection: '+before)
        with self.assertRaisesRegex(ValueError,'Missing unique MEM destination register'):
            inspect_mem_nonzero_register(self.native.replace(self.register,''))
        print('PASS missing MEM flag rejection')

    def test_each_precomputed_input(self):
        for bit in range(5):
            before=f'.I{bit} (ex_instruction[{bit+7}])'
            after=f'.I{bit} (mem_instruction[{bit+7}])'
            self.assertIn(before,self.precompute)
            with self.assertRaisesRegex(ValueError,'EX nonzero source bits differ'):
                inspect_mem_nonzero_register(self.native.replace(self.precompute,self.precompute.replace(before,after)))
            print('PASS MEM flag source rejection: '+str(bit))

    def test_truth_and_consumers(self):
        bits=re.search(r'\.INIT\(32\x27b([01]+)\)',self.precompute)[1]
        with self.assertRaisesRegex(ValueError,'truth table differs'):
            inspect_mem_nonzero_register(self.native.replace(self.precompute,self.precompute.replace(bits,bits[:-1]+'1')))
        altered=re.sub(r'(\.I[0-5]\s*\()mem_rd_nonzero\)',r"\g<1>1'b0)",self.native)
        with self.assertRaisesRegex(ValueError,'no active consumers'):
            inspect_mem_nonzero_register(altered)
        print('PASS MEM flag truth/consumer rejections')

    def test_destination_correspondence(self):
        destination=next(block for block in re.findall(r'GTP_DFF_CE\b[^;]*;',self.native) if '.Q (mem_instruction[7])' in block)
        for before,after in (('.D (ex_instruction[7])','.D (ex_instruction[8])'),('.CE (ex_fire)',".CE (1'b1)"),('.C ('+self.result['clear']+' )',".C (1'b0)")):
            self.assertIn(before,destination)
            with self.assertRaises(ValueError):
                inspect_mem_nonzero_register(self.native.replace(destination,destination.replace(before,after)))
            print('PASS MEM destination correspondence rejection: '+before)

    def test_duplicate_cpu(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous native CPU module'):
            inspect_mem_nonzero_register(self.native+'\nmodule rv32_core; endmodule\n')


if __name__=='__main__':
    unittest.main(verbosity=2)
