import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_forward_data_controls as controls


PROJECT = Path(__file__).resolve().parents[1]
VARIANT = os.environ.get('ZGTC_ADDRESS_VARIANT', 'plain')
if VARIANT not in ('plain', 'select12'):
    raise ValueError('Unsupported address-bypass variant')
CANDIDATE = PROJECT / 'experiments' / 'load_use_address_bypass' / ('rv32_core_' + VARIANT + '.sv')


class AddressBypassTests(unittest.TestCase):
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return PROJECT

    def simulate(self, bubble=1, mutation=None, arithmetic=False):
        source = self.candidate_path().read_text(encoding='utf-8')
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='address-bypass-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            top = 'load_address_arithmetic_tb' if arithmetic else 'load_use_address_bypass_tb'
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output), str(core)]
            if not arithmetic:
                command.append(f'-P{top}.LOAD_USE_BUBBLE={bubble}')
            command += [str(self.project_path() / 'rtl' / (name + '.sv')) for name in ('rv32_decode', 'rv32_alu', 'rv32_machine', 'rv32_btb', 'rv32_muldiv')]
            command.append(str(PROJECT / 'sim' / (top + '.sv')))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(output)], capture_output=True, text=True, timeout=240 if arithmetic else 180)

    def test_branch_conditions_and_independent_general_operands(self):
        for bubble in (0, 1):
            with self.subTest(bubble=bubble):
                result = self.simulate(bubble)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('checks=2631680', result.stdout)

    def test_all_signed_immediates(self):
        result = self.simulate(arithmetic=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('checks=4227072 signed_immediates=4096', result.stdout)

    def test_mutants(self):
        mutations = [
            ('&& !load_address_bypass && mem_valid', '&& mem_valid'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load && ex_decode.immediate==0;'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_store;'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_jalr;'),
            ('&& !equality_branch && !load_address_bypass && mem_valid', '&& mem_valid'),
            ('&& !equality_branch && !load_address_bypass && mem_valid', '&& !ex_decode.is_branch && mem_valid'),
            ("ex_instruction[14:13]==2'b00", "ex_instruction[14:13]==2'b10"),
            ('branch_load_forward=LOAD_USE_BUBBLE!=0', 'branch_load_forward=LOAD_USE_BUBBLE==0'),
            ('mem_load && mem_writes && mem_rd!=0 && !mem_exception;', 'mem_load && mem_writes && mem_rd!=0;'),
            ('mem_load && mem_writes && mem_rd!=0 && !mem_exception;', 'mem_load && mem_writes && !mem_exception;'),
            ('branch_load_forward && ex_decode.uses_rs1 &&', 'branch_load_forward &&'),
            ('ex_rs2==mem_rd ? mem_value : forwarded_b;', 'ex_rs1==mem_rd ? mem_value : forwarded_b;'),
            ('ex_rs1==mem_rd ? mem_value : forwarded_a;', 'ex_rs1==mem_rd ? mem_result : forwarded_a;'),
            ('branch_taken=branch_operand_a==branch_operand_b;', 'branch_taken=branch_operand_a!=branch_operand_b;'),
            ('branch_taken=$signed(forwarded_a)<$signed(forwarded_b);', 'branch_taken=forwarded_a<forwarded_b;'),
            ('branch_taken=$signed(forwarded_a)<$signed(forwarded_b);', 'branch_taken=$signed(branch_operand_a)<$signed(branch_operand_b);'),
            ('branch_taken=forwarded_a>=forwarded_b;', 'branch_taken=branch_operand_a>=branch_operand_b;'),
            ('branch_load_forward=LOAD_USE_BUBBLE!=0 &&', 'branch_load_forward=LOAD_USE_BUBBLE!=0 && d_rsp_valid && !d_rsp_error &&'),
        ]
        if VARIANT == 'plain':
            mutations += [
                ('load_address_bypass ? branch_operand_a : forwarded_a', 'load_address_bypass ? forwarded_a : forwarded_a'),
                ('(load_address_bypass ? branch_operand_a : forwarded_a)+ex_decode.immediate', 'branch_operand_a+ex_decode.immediate'),
            ]
        else:
            mutations += [
                ('load_address_bypass ? load_effective_address : forwarded_a+ex_decode.immediate', 'load_address_bypass ? forwarded_a+ex_decode.immediate : forwarded_a+ex_decode.immediate'),
                ("{1'b0,branch_operand_a[11:0]}+", "{1'b0,forwarded_a[11:0]}+"),
                ('load_address_high=ex_decode.immediate[31] ?', 'load_address_high=!ex_decode.immediate[31] ?'),
                ("load_address_high_plus=branch_operand_a[31:12]+20'd1", "load_address_high_plus=branch_operand_a[31:12]+20'd2"),
                ("load_address_high_minus=branch_operand_a[31:12]-20'd1", "load_address_high_minus=branch_operand_a[31:12]-20'd2"),
                ('(load_address_low[12] ? load_address_high_plus :', '(load_address_low[11] ? load_address_high_plus :'),
                ('load_address_bypass ? load_effective_address : forwarded_a+ex_decode.immediate', 'load_address_bypass ? load_effective_address : branch_operand_a+ex_decode.immediate'),
            ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL load_use_address_bypass', result.stdout + result.stderr)
                self.assertNotIn('incomplete case count', result.stdout + result.stderr)


class AddressBypassPoisonControls(controls.ForwardDataControls):
    def project_path(self):
        return PROJECT / 'build' / ('load-use-address-' + VARIANT + '-stage')

    def candidate_path(self):
        return CANDIDATE




class AddressBypassCachedCoverage(unittest.TestCase):
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return PROJECT / 'build' / ('load-use-address-' + VARIANT + '-stage')

    def test_positive_and_full_bubble_rejection(self):
        stage = self.project_path()
        self.assertTrue((stage / 'build' / 'core_selftest.hex').is_file(), 'Run isolated cached CPU regression first')
        for full_bubble in (False, True):
            source = self.candidate_path().read_text(encoding='utf-8')
            if full_bubble:
                before = 'LOAD_USE_BUBBLE!=0 && !equality_branch && !load_address_bypass && mem_valid'
                self.assertEqual(source.count(before), 1)
                source = source.replace(before, 'LOAD_USE_BUBBLE!=0 && mem_valid')
            with self.subTest(full_bubble=full_bubble), tempfile.TemporaryDirectory(prefix='address-cache-') as directory:
                work = Path(directory)
                core = work / 'rv32_core.sv'
                core.write_text(source, encoding='utf-8')
                output = work / 'test.vvp'
                parameters = dict(LOAD_USE_BUBBLE=1, PREDICTOR=1, ENABLE_CACHE=1, CACHE_SETS=6, ICACHE_SET_BITS=9,
                    FAST_ICACHE_HIT=1, FAST_DCACHE_READ=1, FAST_DCACHE_WRITE=1, EARLY_D_REQUEST=1, FETCH_OVERLAP=1, DATA_OVERLAP=1, BTB_INDEX_BITS=8)
                command = ['iverilog', '-g2012', '-s', 'cached_core_tb', '-o', str(output)]
                command += [f'-Pcached_core_tb.{name}={value}' for name, value in parameters.items()]
                command += [str(path) for path in sorted((stage / 'rtl').glob('*.sv')) if path.name != 'rv32_core.sv']
                command += [str(core), str(stage / 'sim' / 'cached_core_tb.sv')]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                result = subprocess.run(['vvp', str(output), f'+firmware={stage / "build" / "core_selftest.hex"}',
                    f'+trace={work / "test.trace"}', f'+memory_out={work / "test.memory"}'], capture_output=True, text=True, timeout=60)
                if full_bubble:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('non-bypass consumer held on load completion', result.stdout)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    checked = subprocess.run(['python3', str(PROJECT / 'scripts' / 'check_trace.py'),
                        str(stage / 'build' / 'core_selftest.bin'), str(work / 'test.trace'), '--memory', str(work / 'test.memory')],
                        capture_output=True, text=True, timeout=30)
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                    self.assertIn('PASS reference', checked.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
