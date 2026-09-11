import subprocess
import tempfile
import unittest
from pathlib import Path

import test_load_use_address_bypass as address
import test_forward_data_controls as controls

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'build' / 'wb-match-predecode-stage'
CANDIDATE = PROJECT / 'experiments' / 'wb_match_predecode' / 'rv32_core.sv'

class WbPaths:
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return STAGE

class WbMatrixTests(WbPaths, address.AddressBypassTests):
    def simulate(self, bubble=1, mutation=None, arithmetic=False):
        source = CANDIDATE.read_text(encoding='utf-8')
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='wb-match-matrix-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            top = 'load_address_arithmetic_tb' if arithmetic else 'load_use_address_bypass_tb'
            bench = PROJECT / 'sim' / (top + '.sv') if arithmetic else PROJECT / 'experiments' / 'wb_match_predecode' / (top + '.sv')
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output), str(core)]
            if not arithmetic:
                command.append(f'-P{top}.LOAD_USE_BUBBLE={bubble}')
            command += [str(STAGE / 'rtl' / (name + '.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(bench))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp',str(output)], capture_output=True, text=True, timeout=300)

    def test_mutants(self):
        mutations = [
            ('if(ex_wb_match_a) forwarded_a=wb_data;', 'if(ex_wb_match_a) forwarded_a=mem_value;'),
            ('if(ex_wb_match_b) forwarded_b=wb_data;', 'if(ex_wb_match_a) forwarded_b=wb_data;'),
            ('if(ex_wb_match_a) forwarded_a=wb_data;', 'if(!ex_wb_match_a) forwarded_a=wb_data;'),
            ('if(ex_wb_match_a) forwarded_a=wb_data;', 'if(ex_wb_match_a && !mem_valid) forwarded_a=wb_data;'),
            ('&& !load_address_bypass && mem_valid', '&& mem_valid'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_store;'),
            ('load_address_bypass=ex_decode.is_load;', 'load_address_bypass=ex_decode.is_load || ex_decode.is_jalr;'),
            ('branch_load_forward && ex_decode.uses_rs1 &&', 'branch_load_forward &&'),
            ('ex_rs1==mem_rd ? mem_value : forwarded_a;', 'ex_rs1==mem_rd ? mem_result : forwarded_a;'),
            ('branch_taken=branch_operand_a==branch_operand_b;', 'branch_taken=branch_operand_a!=branch_operand_b;'),
            ('branch_taken=$signed(forwarded_a)<$signed(forwarded_b);', 'branch_taken=$signed(branch_operand_a)<$signed(branch_operand_b);'),
            ('load_address_bypass ? branch_operand_a : forwarded_a', 'load_address_bypass ? forwarded_a : forwarded_a'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL load_use_address_bypass', result.stdout + result.stderr)
                self.assertNotIn('incomplete case count', result.stdout + result.stderr)

class WbStateTests(unittest.TestCase):
    def simulate(self, full=False, mutation=None):
        source = CANDIDATE.read_text(encoding='utf-8')
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='wb-match-state-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            command = ['iverilog','-g2012','-s','wb_match_state_tb',f'-Pwb_match_state_tb.FULL_SWEEP={int(full)}','-o',str(output),str(core)]
            command += [str(STAGE / 'rtl' / (name + '.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(PROJECT / 'sim' / 'wb_match_state_tb.sv'))
            compiled = subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(output)],capture_output=True,text=True,timeout=600 if full else 60)

    def test_all_pipeline_transition_inputs(self):
        result = self.simulate(full=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('cases=1048576 checks=4194304',result.stdout)
        self.assertIn('controls=ffffffff',result.stdout)
        print(result.stdout.strip())

    def test_tag_generation_mutants(self):
        mutations = [
            ('(id_fire ? id_rs1 : ex_rs1)==mem_rd;', 'ex_rs1==mem_rd;'),
            ('(id_fire ? id_rs1 : ex_rs1)==mem_rd;', 'id_rs1==mem_rd;'),
            ('(id_fire ? id_rs2 : ex_rs2)==mem_rd;', '(id_fire ? id_rs1 : ex_rs1)==mem_rd;'),
            ('ex_wb_match_a<=mem_fire && !mem_fault &&', 'ex_wb_match_a<=mem_fire &&'),
            ('ex_wb_match_b<=mem_fire && !mem_fault &&', 'ex_wb_match_b<=mem_fire &&'),
            ('ex_wb_match_a<=mem_fire &&', 'ex_wb_match_a<='),
            ('ex_wb_match_b<=mem_fire && !mem_fault && mem_writes &&', 'ex_wb_match_b<=mem_fire && !mem_fault &&'),
            ('ex_wb_match_a<=mem_fire && !mem_fault && mem_writes && mem_rd!=0 &&', 'ex_wb_match_a<=mem_fire && !mem_fault && mem_writes &&'),
            ('ex_wb_match_a<=mem_fire && !mem_fault &&', 'ex_wb_match_a<=mem_fire && !mem_fault && !mem_flush &&'),
            ('ex_wb_match_a<=0; ex_wb_match_b<=0;', 'ex_wb_match_a<=1; ex_wb_match_b<=0;'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('FAIL wb_match_state',result.stdout+result.stderr)
                self.assertNotIn('incomplete case coverage',result.stdout+result.stderr)

class WbPoisonTests(WbPaths, controls.ForwardDataControls):
    pass

class WbCachedTests(WbPaths, address.AddressBypassCachedCoverage):
    pass

if __name__ == '__main__':
    unittest.main(verbosity=2)
