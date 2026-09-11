import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_load_use_address_bypass as address

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'build/early-direct-carry8-stage'
PARENT = ROOT / 'experiments/early_direct_redirect/rv32_core.sv'
CANDIDATE = ROOT / 'experiments/early_direct_carry8/rv32_core.sv'

class EarlyDirectCarry8Tests(address.AddressBypassTests):
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return STAGE

    def simulate(self, bubble=1, mutation=None, arithmetic=False):
        source = self.candidate_path().read_text(encoding='utf-8')
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='load-route-matrix-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            top = 'load_address_arithmetic_tb' if arithmetic else 'load_use_address_bypass_tb'
            bench = ROOT / 'sim' / (top + '.sv') if arithmetic else ROOT / 'experiments' / 'load_route_predecode' / (top + '.sv')
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output), str(core)]
            if not arithmetic:
                command.append(f'-P{top}.LOAD_USE_BUBBLE={bubble}')
            command += [str(self.project_path() / 'rtl' / (name + '.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(bench))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp',str(output)], capture_output=True, text=True, timeout=300)

    def run_arithmetic(self, source):
        with tempfile.TemporaryDirectory(prefix='load-address-carry16-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            command = ['iverilog','-g2012','-s','load_address_carry16_tb','-o',str(output),str(core)]
            command += [str(STAGE / 'rtl' / (name+'.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(ROOT / 'sim/load_address_carry16_tb.sv'))
            compiled = subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(output)],capture_output=True,text=True,timeout=90)

    def test_original_and_candidate_full_width_arithmetic(self):
        for path in (PARENT,CANDIDATE):
            with self.subTest(source=str(path)):
                result = self.run_arithmetic(path.read_text(encoding='utf-8'))
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('PASS load_address_carry16 checks=332320 operations=10',result.stdout)
                self.assertEqual(result.stdout.count('COVER load_address_carry16 operation='),10)
                print(result.stdout.strip())

    def test_only_address_logic_changes(self):
        parent = PARENT.read_text(encoding='utf-8')
        candidate = CANDIDATE.read_text(encoding='utf-8')
        self.assertEqual(hashlib.sha256(PARENT.read_bytes()).hexdigest().upper(), 'F48EF3341133BBBFF7155A132472B8CF8766A23F9B246F30DD136935BC14C535')
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest().upper(), 'FCD29C622EFA23A666398EC27324A97A2291D1079A24CC6949FE91A74E1DFF99')
        self.assertEqual(CANDIDATE.read_bytes(), (STAGE / 'rtl/rv32_core.sv').read_bytes())
        original = "    wire [16:0] address_low={1'b0,address_operand[15:0]}+{1'b0,ex_decode.immediate[15:0]};\n    (* syn_keep=1 *) wire [15:0] address_high_zero=address_operand[31:16]+ex_decode.immediate[31:16];\n    (* syn_keep=1 *) wire [15:0] address_high_one=address_operand[31:16]+ex_decode.immediate[31:16]+16'd1;\n    wire [31:0] effective_address={address_low[16] ? address_high_one : address_high_zero,address_low[15:0]};"
        replacement = "    wire [8:0] address_byte0={1'b0,address_operand[7:0]}+{1'b0,ex_decode.immediate[7:0]};\n    (* syn_keep=1 *) wire [8:0] address_byte1_zero={1'b0,address_operand[15:8]}+{1'b0,ex_decode.immediate[15:8]};\n    (* syn_keep=1 *) wire [7:0] address_byte1_one=address_operand[15:8]+ex_decode.immediate[15:8]+8'd1;\n    (* syn_keep=1 *) wire [8:0] address_byte2_zero={1'b0,address_operand[23:16]}+{1'b0,ex_decode.immediate[23:16]};\n    (* syn_keep=1 *) wire [7:0] address_byte2_one=address_operand[23:16]+ex_decode.immediate[23:16]+8'd1;\n    (* syn_keep=1 *) wire [7:0] address_byte3_zero=address_operand[31:24]+ex_decode.immediate[31:24];\n    (* syn_keep=1 *) wire [7:0] address_byte3_one=address_operand[31:24]+ex_decode.immediate[31:24]+8'd1;\n    wire address_propagate1=&(address_operand[15:8]^ex_decode.immediate[15:8]);\n    wire address_propagate2=&(address_operand[23:16]^ex_decode.immediate[23:16]);\n    wire address_carry16=address_byte1_zero[8] || (address_propagate1 && address_byte0[8]);\n    wire address_carry24=address_byte2_zero[8] || (address_propagate2 && address_byte1_zero[8]) ||\n        (address_propagate2 && address_propagate1 && address_byte0[8]);\n    wire [31:0] effective_address={address_carry24 ? address_byte3_one : address_byte3_zero,\n        address_carry16 ? address_byte2_one : address_byte2_zero[7:0],\n        address_byte0[8] ? address_byte1_one : address_byte1_zero[7:0],address_byte0[7:0]};"
        self.assertEqual(parent.count(original), 1)
        self.assertEqual(candidate.count(replacement), 1)
        self.assertEqual(candidate.replace(replacement, original), parent)

    def test_route_fixture_only_adds_current_registered_state(self):
        original = (ROOT / 'sim/load_use_address_bypass_tb.sv').read_text(encoding='utf-8')
        routed = (ROOT / 'experiments/load_route_predecode/load_use_address_bypass_tb.sv').read_text(encoding='utf-8')
        first = '    integer checks=0;'
        second = '        force dut.mem_funct3=memory_funct3;'
        self.assertEqual(original.count(first),1)
        self.assertEqual(original.count(second),1)
        expected = original.replace(first,first+'\n    wire [16:0] forced_load_route=dut.decode_load_route(memory_funct3,memory_address[1:0]);').replace(second,second+'\n        force dut.mem_load_route=forced_load_route;')
        self.assertEqual(routed,expected)

    def test_mutants(self):
        source = CANDIDATE.read_text(encoding='utf-8')
        mutations = (
            ('lost_byte1_carry', 'address_byte0[8] ? address_byte1_one', "1'b0 ? address_byte1_one"),
            ('lost_byte2_carry', 'address_carry16 ? address_byte2_one', "1'b0 ? address_byte2_one"),
            ('lost_byte3_carry', 'address_carry24 ? address_byte3_one', "1'b0 ? address_byte3_one"),
            ('lost_propagated_carry', ' ||\n        (address_propagate2 && address_propagate1 && address_byte0[8])', ''),
            ('wrong_propagate', 'address_propagate1=&(address_operand[15:8]^ex_decode.immediate[15:8])', 'address_propagate1=|(address_operand[15:8]^ex_decode.immediate[15:8])'),
            ('wrong_byte3_one', "address_byte3_one=address_operand[31:24]+ex_decode.immediate[31:24]+8'd1", "address_byte3_one=address_operand[31:24]+ex_decode.immediate[31:24]-8'd1"),
            ('wrong_carry_bit', 'address_byte0[8] ? address_byte1_one', 'address_byte0[7] ? address_byte1_one'),
            ('lost_top_immediate', 'address_byte3_zero=address_operand[31:24]+ex_decode.immediate[31:24]', 'address_byte3_zero=address_operand[31:24]'),
            ('reversed_operand_sources', 'load_address_bypass ? branch_operand_a : forwarded_a', 'load_address_bypass ? forwarded_a : branch_operand_a'),
        )
        for name, before, after in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(source.count(before), 1)
                result = self.run_arithmetic(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL load_address_carry16', result.stdout + result.stderr)
                self.assertNotIn('missing carry/alignment coverage', result.stdout + result.stderr)
                self.assertNotIn('incomplete case count', result.stdout + result.stderr)
                print('PASS byte carry-select mutant rejected: ' + name)

if __name__ == '__main__':
    unittest.main(verbosity=2)
