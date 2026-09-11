import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_mul_request_capture as request_controls


PROJECT = Path(__file__).resolve().parents[1]
SOURCES = {'csa': '0A318CBB26FC16ECCFA4C556C5550BD5E816EC186C9619F01EFC0CC80DC4769E',
           'csa_select16': '0901AFDB721FC22C91C5C1C667AD241550EC909DC9285BBEB2EA8107D1B0A73A'}


def candidate_path(variant):
    return PROJECT / 'experiments' / 'mul_carry_save' / ('rv32_muldiv_' + variant + '.sv')


class CarrySaveArithmetic(unittest.TestCase):
    def simulate(self, variant, mutation=None):
        source_path = candidate_path(variant)
        self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest().upper(), SOURCES[variant])
        source = source_path.read_text(encoding='utf-8')
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        original = PROJECT / 'rtl' / 'rv32_muldiv.sv'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest().upper(), '1079EF43882452422508E2247AF93699B357E3EAAF0B3118A8C95E5434457DC5')
        with tempfile.TemporaryDirectory(prefix='mul-csa-') as directory:
            work = Path(directory)
            candidate = work / 'rv32_muldiv.sv'
            candidate.write_text(source, encoding='utf-8')
            reference = work / 'reference.sv'
            reference.write_text(original.read_text(encoding='utf-8').replace('module rv32_muldiv (', 'module rv32_muldiv_reference ('), encoding='utf-8')
            output = work / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'mul_carry_save_tb', '-o', str(output), str(candidate), str(reference), str(PROJECT / 'sim' / 'mul_carry_save_tb.sv')]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=60)

    def test_valid_partial_products_against_reference_and_wide_multiply(self):
        for variant in SOURCES:
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS mul_carry_save checks=263168', result.stdout)

    def test_arithmetic_mutations(self):
        mutations = [
            ('csa', ('{{14{product_low_high[33]}},product_low_high}', "{14'b0,product_low_high}")),
            ('csa', ('{{14{product_high_low[33]}},product_high_low}', "{14'b0,product_high_low}")),
            ('csa', ('product_outer={product_high_high,product_low_low[31:16]}', 'product_outer={product_high_high,product_low_low[15:0]}')),
            ('csa', (')) << 1;', ')) << 2;')),
            ('csa', ('product_upper=product_sum+product_carry;', 'product_upper=product_sum;')),
            ('csa', ('product_cross_a^product_cross_b^product_outer', 'product_cross_a|product_cross_b|product_outer')),
            ('csa', ('product={product_upper,product_low_low[15:0]}', 'product={product_upper,product_low_low[31:16]}')),
            ('csa_select16', ('product_add_low[16] ? product_add_middle_one : product_add_middle_zero', 'product_add_low[16] ? product_add_middle_zero : product_add_middle_one')),
            ('csa_select16', ('product_add_middle[16] ? product_add_high_one : product_add_high_zero', 'product_add_middle[16] ? product_add_high_zero : product_add_high_one')),
            ('csa_select16', ('+17\'d1;', '+17\'d0;')),
        ]
        for variant, mutation in mutations:
            with self.subTest(variant=variant, mutation=mutation):
                result = self.simulate(variant, mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL mul_carry_save operation=', result.stdout + result.stderr)


class CarrySaveRequestControls(request_controls.MultiplyRequestControls):
    def candidate_path(self):
        return candidate_path('csa')


class CarrySelectRequestControls(request_controls.MultiplyRequestControls):
    def candidate_path(self):
        return candidate_path('csa_select16')


if __name__ == '__main__':
    unittest.main(verbosity=2)

