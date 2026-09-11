import os
from pathlib import Path
import unittest

import test_load_use_address_bypass as address
import test_forward_data_controls as controls

PROJECT = Path(__file__).resolve().parents[1]
VARIANT = os.environ.get('ZGTC_OPERAND_VARIANT', 'priority')
if VARIANT not in ('priority', 'onehot'):
    raise ValueError('Unsupported operand-select variant')
CANDIDATE = PROJECT / 'experiments' / 'load_operand_select' / ('rv32_core_' + VARIANT + '.sv')
STAGE = PROJECT / 'build' / ('load-operand-select-' + VARIANT + '-stage')

class SelectorPaths:
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return STAGE

class SelectorMatrixTests(SelectorPaths, address.AddressBypassTests):
    def test_only_special_operand_selection_changes(self):
        baseline = (PROJECT / 'experiments' / 'load_use_address_bypass' / 'rv32_core_plain.sv').read_text(encoding='utf-8')
        candidate = CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(baseline.split('    wire branch_load_forward=')[0], candidate.split('    wire special_mem_forward=')[0])
        self.assertEqual(baseline.split('    reg branch_taken;')[1] + '\n', candidate.split('    reg branch_taken;')[1])
        self.assertEqual(candidate.count('effective_address=(load_address_bypass ? branch_operand_a : forwarded_a)+ex_decode.immediate;'), 1)

    def test_mutants(self):
        mutations = [
            ('special_mem_forward=mem_valid && mem_writes && mem_rd!=0 && !mem_exception;', 'special_mem_forward=mem_valid && mem_writes && mem_rd!=0;'),
            ('special_mem_forward=mem_valid &&', 'special_mem_forward='),
            ('special_mem_forward=mem_valid && mem_writes &&', 'special_mem_forward=mem_valid &&'),
            ('special_mem_forward=mem_valid &&', 'special_mem_forward=mem_load && mem_valid &&'),
            ('special_mem_forward=mem_valid &&', 'special_mem_forward=d_rsp_valid && !d_rsp_error && mem_valid &&'),
            ('special_wb_forward=wb_valid &&', 'special_wb_forward='),
            ('special_wb_forward=wb_valid && wb_writes &&', 'special_wb_forward=wb_valid &&'),
            ('special_use_a=ex_decode.uses_rs1 && ex_rs1!=0;', 'special_use_a=ex_rs1!=0;'),
            ('special_use_a=ex_decode.uses_rs1 && ex_rs1!=0;', 'special_use_a=ex_decode.uses_rs1;'),
            ('special_use_b=ex_decode.uses_rs2 && ex_rs2!=0;', 'special_use_b=ex_rs2!=0;'),
            ('special_use_b=ex_decode.uses_rs2 && ex_rs2!=0;', 'special_use_b=ex_decode.uses_rs2;'),
            ('special_mem_a=special_use_a && special_mem_forward && ex_rs1==mem_rd;', 'special_mem_a=special_use_a && special_mem_forward && ex_rs1==wb_rd;'),
            ('special_mem_b=special_use_b && special_mem_forward && ex_rs2==mem_rd;', 'special_mem_b=special_use_b && special_mem_forward && ex_rs1==mem_rd;'),
            ('&& !load_address_bypass && mem_valid', '&& mem_valid'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_store;'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_jalr;'),
            ('branch_taken=branch_operand_a==branch_operand_b;', 'branch_taken=branch_operand_a!=branch_operand_b;'),
            ('branch_taken=$signed(forwarded_a)<$signed(forwarded_b);', 'branch_taken=$signed(branch_operand_a)<$signed(branch_operand_b);'),
            ('load_address_bypass ? branch_operand_a : forwarded_a', 'load_address_bypass ? forwarded_a : forwarded_a'),
        ]
        if VARIANT == 'priority':
            mutations += [
                ('special_mem_a ? mem_value : special_wb_a ? wb_data :', 'special_wb_a ? wb_data : special_mem_a ? mem_value :'),
                ('special_mem_a ? mem_value :', 'special_mem_a ? mem_result :'),
                ('special_wb_a ? wb_data :', 'special_wb_a ? ex_operand_a :'),
            ]
        else:
            mutations += [
                ('ex_rs1==wb_rd && !special_mem_a;', 'ex_rs1==wb_rd;'),
                ('ex_rs2==wb_rd && !special_mem_b;', 'ex_rs2==wb_rd;'),
                ('special_register_a=special_use_a && !special_mem_a && !special_wb_a;', 'special_register_a=special_use_a && !special_wb_a;'),
                ('special_register_b=special_use_b && !special_mem_b && !special_wb_b;', 'special_register_b=special_use_b && !special_mem_b;'),
                ('{32{special_mem_a}} & mem_value', '{32{special_mem_a}} & mem_result'),
                ('{32{special_wb_a}} & wb_data', '{32{special_wb_a}} & ex_operand_a'),
            ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL load_use_address_bypass', result.stdout + result.stderr)
                self.assertNotIn('incomplete case count', result.stdout + result.stderr)

class SelectorPoisonTests(SelectorPaths, controls.ForwardDataControls):
    pass

class SelectorCachedTests(SelectorPaths, address.AddressBypassCachedCoverage):
    pass

if __name__ == '__main__':
    unittest.main(verbosity=2)
