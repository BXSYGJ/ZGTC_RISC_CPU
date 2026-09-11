import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import test_early_direct_carry8_redirect as redirect

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'experiments/early_compare_byte/rv32_core.sv'
PARENT = ROOT / 'experiments/early_direct_carry8/rv32_core.sv'
STAGE = ROOT / 'build/early-compare-byte-stage'
BENCH = ROOT / 'sim/early_compare_byte_tb.sv'
CORE_HASH = '3E431AA8FA2B91A933C2B51163366EA372CCF0B2DD95B1B9F6C0CC3D5D9599AC'
redirect.CORE = CORE
redirect.STAGE = STAGE


class ByteRedirectTests(redirect.EarlyDirectRedirectTests):
    def test_canonical_and_staged_source(self):
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest().upper(), CORE_HASH)
        self.assertEqual(CORE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())


class ByteCompareTests(unittest.TestCase):
    def run_probe(self, source):
        begin = source.index('    (* syn_keep=1 *) wire [3:0] early_byte_equal;')
        end = source.index('    reg early_taken;',begin)
        block = source[begin:end]
        for name in ('early_equal','early_unsigned_less','early_signed_less'):
            block = block.replace('wire '+name+'=', 'assign '+name+'=')
        wrapper = 'module early_compare_probe(input [31:0] early_operand_a,early_operand_b,output early_equal,early_unsigned_less,early_signed_less);\n' + block + 'endmodule\n'
        with tempfile.TemporaryDirectory(prefix='early-compare-byte-') as temporary:
            folder = Path(temporary)
            probe = folder / 'probe.sv'
            probe.write_text(wrapper,encoding='utf-8')
            image = folder / 'test.vvp'
            compiled = subprocess.run(['iverilog','-g2012','-s','early_compare_byte_tb','-o',str(image),str(probe),str(BENCH)],capture_output=True,text=True,timeout=60)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=120)

    def test_exact_comparator_only_delta(self):
        parent = PARENT.read_text(encoding='utf-8')
        source = CORE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(),'FCD29C622EFA23A666398EC27324A97A2291D1079A24CC6949FE91A74E1DFF99')
        begin = source.index('    (* syn_keep=1 *) wire [3:0] early_byte_equal;')
        end = source.index('    reg early_taken;',begin)
        restored = source[:begin]+source[end:]
        for replacement,original in (
            ('early_equal','early_operand_a==early_operand_b'),
            ('!early_equal','early_operand_a!=early_operand_b'),
            ('early_signed_less','$signed(early_operand_a)<$signed(early_operand_b)'),
            ('!early_signed_less','$signed(early_operand_a)>=$signed(early_operand_b)'),
            ('early_unsigned_less','early_operand_a<early_operand_b'),
            ('!early_unsigned_less','early_operand_a>=early_operand_b'),
        ):
            before='early_taken='+replacement+';'
            self.assertEqual(restored.count(before),1)
            restored=restored.replace(before,'early_taken='+original+';')
        self.assertEqual(restored,parent)

    def test_actual_source_comparison(self):
        result = self.run_probe(CORE.read_text(encoding='utf-8'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS early_compare_byte checks=786624 byte_pairs=262144 random_pairs=65536',result.stdout)
        self.assertEqual(result.stdout.count('COVER early_compare_byte lane='),4)
        print(result.stdout.strip())

    def test_runtime_mutations(self):
        source = CORE.read_text(encoding='utf-8')
        mutations = (
            ('wrong_byte_order','early_byte_less[3] ||','early_byte_less[0] ||'),
            ('ignore_top_equal','early_byte_equal[3] && early_byte_less[2]','early_byte_less[2]'),
            ('ignore_middle_equal','early_byte_equal[2] && early_byte_less[1]','early_byte_less[1]'),
            ('ignore_low_equal','early_byte_equal[1] && early_byte_less[0]','early_byte_less[0]'),
            ('non_strict_byte','early_operand_a[compare_byte*8+:8]<early_operand_b','early_operand_a[compare_byte*8+:8]<=early_operand_b'),
            ('wrong_equal_reduce','early_equal=&early_byte_equal','early_equal=|early_byte_equal'),
            ('wrong_sign','? early_operand_a[31] : early_unsigned_less','? early_operand_b[31] : early_unsigned_less'),
            ('unsigned_as_signed','(early_operand_a[31]^early_operand_b[31]) ? early_operand_a[31] : early_unsigned_less','early_unsigned_less'),
        )
        for name,before,after in mutations:
            with self.subTest(name=name):
                self.assertEqual(source.count(before),1)
                result=self.run_probe(source.replace(before,after))
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('FAIL early_compare_byte first=',result.stdout)
                self.assertNotIn('incomplete coverage',result.stdout)
                print('PASS byte comparator runtime mutant rejected: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
