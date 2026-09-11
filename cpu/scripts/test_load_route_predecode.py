import subprocess
import tempfile
import unittest
from pathlib import Path

import test_load_use_address_bypass as address
import test_forward_data_controls as controls

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'build' / 'load-route-predecode-stage'
CANDIDATE = PROJECT / 'experiments' / 'load_route_predecode' / 'rv32_core.sv'

class RoutePaths:
    def candidate_path(self):
        return CANDIDATE

    def project_path(self):
        return STAGE

class RouteMatrixTests(RoutePaths, address.AddressBypassTests):
    def simulate(self, bubble=1, mutation=None, arithmetic=False):
        source = CANDIDATE.read_text(encoding='utf-8')
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
            bench = PROJECT / 'sim' / (top + '.sv') if arithmetic else PROJECT / 'experiments' / 'load_route_predecode' / (top + '.sv')
            command = ['iverilog', '-g2012', '-s', top, '-o', str(output), str(core)]
            if not arithmetic:
                command.append(f'-P{top}.LOAD_USE_BUBBLE={bubble}')
            command += [str(STAGE / 'rtl' / (name + '.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(bench))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp',str(output)], capture_output=True, text=True, timeout=300)

    def test_exact_scoped_changes(self):
        baseline = (PROJECT / 'build/load-use-address-plain-stage/rtl/rv32_core.sv').read_text()
        candidate = CANDIDATE.read_text()
        self.assertEqual(candidate.split('    reg [31:0] mem_value;')[0], baseline.split('    reg [31:0] mem_value,load_shifted;')[0])
        before_start = baseline.index('    always @* begin\n        load_shifted=')
        before_end = baseline.index('    always @* begin\n        forwarded_a=', before_start)
        candidate_start = candidate.index('    always @* begin\n        mem_value=mem_load ?')
        candidate_end = candidate.index('    always @* begin\n        forwarded_a=', candidate_start)
        restored = candidate[:candidate_start] + baseline[before_start:before_end] + candidate[candidate_end:]
        prefix_start = restored.index('    reg [31:0] mem_value;')
        prefix_end = restored.index('    wire branch_load_forward=', prefix_start)
        restored = restored[:prefix_start] + '    reg [31:0] mem_value,load_shifted;\n' + restored[prefix_end:]
        restored = restored.replace(" mem_load_route<=decode_load_route(3'd0,2'd0);", '')
        restored = restored.replace(' mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);', '')
        self.assertEqual(restored, baseline)

    def test_mutants(self):
        mutations = [
            ('mem_load ? {load_byte3,load_byte2,load_byte1,load_byte0} : mem_result', 'mem_load ? {load_byte0,load_byte2,load_byte1,load_byte3} : mem_result'),
            ('mem_load ? {load_byte3,load_byte2,load_byte1,load_byte0} : mem_result', "mem_load ? {load_byte3,load_byte2,load_byte1,load_byte0} : 32'b0"),
            ('load_format==0 || load_format==4', 'load_format==0'),
            ('load_format==1 || load_format==5', 'load_format==1'),
            ('word_format=load_format==2;', 'word_format=load_format==3;'),
            ('decode_load_route[13:10]={4{load_format==0}} & byte_lane;', "decode_load_route[13:10]=4'b0;"),
            ('decode_load_route[16:14]={3{load_format==1}} & byte_lane[2:0];', "decode_load_route[16:14]=3'b0;"),
            ('({8{mem_load_route[6]}} & d_rsp_data[31:24])', '({8{mem_load_route[6]}} & d_rsp_data[23:16])'),
            ('load_byte2=({8{mem_load_route[7]}} & d_rsp_data[23:16])', 'load_byte2=({8{mem_load_route[7]}} & d_rsp_data[31:24])'),
            ('load_address_bypass ? branch_operand_a : forwarded_a', 'load_address_bypass ? forwarded_a : forwarded_a'),
            ('branch_load_forward && ex_decode.uses_rs1 &&', 'branch_load_forward &&'),
            ('branch_taken=branch_operand_a==branch_operand_b;', 'branch_taken=branch_operand_a!=branch_operand_b;'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL load_use_address_bypass', result.stdout + result.stderr)
                self.assertNotIn('incomplete case count', result.stdout + result.stderr)


class RouteStateTests(unittest.TestCase):
    def simulate(self, full=False, mutation=None):
        source = CANDIDATE.read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='load-route-state-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            output = work / 'test.vvp'
            command = ['iverilog','-g2012','-s','load_route_state_tb', f'-Pload_route_state_tb.FULL_SWEEP={int(full)}','-o',str(output),str(core)]
            command += [str(STAGE / 'rtl' / (name + '.sv')) for name in ('rv32_decode','rv32_alu','rv32_machine','rv32_btb','rv32_muldiv')]
            command.append(str(PROJECT / 'sim/load_route_state_tb.sv'))
            compiled = subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
            return subprocess.run(['vvp',str(output)],capture_output=True,text=True,timeout=300)

    def test_state_transitions_and_response_bits(self):
        result = self.simulate(full=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('cases=16384 state_checks=32768 data_checks=1179648 controls=ff',result.stdout)
        print(result.stdout.strip())

    def test_route_capture_mutations(self):
        mutations = (
            ("mem_load_route<=decode_load_route(3'd0,2'd0)", "mem_load_route<=17'b0"),
            ('mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0])', 'mem_load_route<=decode_load_route(mem_funct3,effective_address[1:0])'),
            ('mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0])', 'mem_load_route<=decode_load_route(ex_instruction[14:12],mem_address[1:0])'),
            ('mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);', 'if(!mem_flush) mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);'),
            ('mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);', 'if(ex_decode.is_load) mem_load_route<=decode_load_route(ex_instruction[14:12],effective_address[1:0]);'),
            ('if(mem_fire) begin mem_valid<=0; mem_sent<=0; end', "if(mem_fire) begin mem_valid<=0; mem_sent<=0; mem_load_route<=17'b0; end"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('FAIL load_route_state',result.stdout+result.stderr)
                self.assertNotIn('incomplete coverage',result.stdout+result.stderr)


class RoutePoisonTests(RoutePaths, controls.ForwardDataControls):
    pass


class RouteCachedTests(RoutePaths, address.AddressBypassCachedCoverage):
    pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
