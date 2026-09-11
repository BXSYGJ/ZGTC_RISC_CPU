import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_forward_data_controls as controls_tests


PROJECT = Path(__file__).resolve().parents[1]
SOURCES = {
    'baseline': ('rtl/rv32_core.sv', 'C4F0EF80E634F153F5BF1CB2B0F9BB314432333BF9DC93E1A8E9F6E1C2CC2346'),
    'mask': ('experiments/forward_parallel/rv32_core_mask.sv', '0BC6382F11826855F587D977C75AD67F37E0EA03C21471AAC76445B3A4127291'),
    'raw_word': ('experiments/forward_parallel/rv32_core_raw_word.sv', '08A722CF39D507E2A25B9B8CCFBF1FCCEA0DF8BDB6AA6165A47C6F8F4B9C303C'),
}


class ForwardParallelTests(unittest.TestCase):
    def simulate(self, variant, bubble=0, mutation=None):
        relative, expected_hash = SOURCES[variant]
        data = (PROJECT / relative).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest().upper(), expected_hash)
        source = data.decode()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='forward-parallel-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            image = work / 'test.vvp'
            command = ['iverilog', '-g2012', '-s', 'forward_parallel_tb', '-o', str(image),
                       f'-Pforward_parallel_tb.LOAD_USE_BUBBLE={bubble}', str(core)]
            command += [str(PROJECT / 'rtl' / (name + '.sv')) for name in
                        ('rv32_decode', 'rv32_alu', 'rv32_machine', 'rv32_btb', 'rv32_muldiv')]
            command.append(str(PROJECT / 'sim/forward_parallel_tb.sv'))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=120)

    def test_all_priorities_modes_load_formats_and_alignments(self):
        for variant in SOURCES:
            for bubble in (0, 1):
                with self.subTest(variant=variant, bubble=bubble):
                    result = self.simulate(variant, bubble)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f'PASS forward_parallel checks=65792 bubble={bubble}', result.stdout)
        print('PASS394752 forwarding priority/load-format comparisons across baseline and two candidates')

    def test_compiled_priority_and_raw_word_mutations(self):
        mutations = (
            ('mask', 0, ('forward_wb_a=use_operand_a && !forward_mem_a', 'forward_wb_a=use_operand_a')),
            ('mask', 0, ('forward_wb_b=use_operand_b && !forward_mem_b', 'forward_wb_b=use_operand_b')),
            ('mask', 0, ('forward_ex_a=use_operand_a && !forward_mem_a && !forward_wb_a', 'forward_ex_a=use_operand_a')),
            ('mask', 0, ('use_operand_a=ex_rs1!=0 &&', "use_operand_a=1'b1 &&")),
            ('mask', 0, ('use_operand_b=ex_rs2!=0 &&', "use_operand_b=1'b1 &&")),
            ('mask', 0, ('&& ex_decode.uses_rs1;', "&& 1'b1;")),
            ('mask', 0, ('({32{forward_wb_a}} & wb_data)', '({32{forward_wb_a}} & ex_operand_a)')),
            ('mask', 1, ('(!mem_load || LOAD_USE_BUBBLE==0)', "1'b1")),
            ('mask', 0, ('&& !mem_exception &&', '&&')),
            ('raw_word', 0, ('&& mem_address[1:0]==0;', ';')),
            ('raw_word', 0, ('&& mem_funct3==2 &&', '&& mem_funct3==1 &&')),
            ('raw_word', 0, ('({32{forward_mem_a && forward_raw_word}} & d_rsp_data)', '({32{forward_mem_a && forward_raw_word}} & mem_result)')),
        )
        for variant, bubble, mutation in mutations:
            with self.subTest(variant=variant, bubble=bubble, mutation=mutation):
                result = self.simulate(variant, bubble, mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('FAIL forward_parallel', result.stdout + result.stderr)
        print('PASS12 compiled forwarding priority/raw-word mutations rejected')


class ForwardMaskControls(controls_tests.ForwardDataControls):
    def candidate_path(self):
        return PROJECT / SOURCES['mask'][0]


class ForwardRawWordControls(controls_tests.ForwardDataControls):
    def candidate_path(self):
        return PROJECT / SOURCES['raw_word'][0]


if __name__ == '__main__':
    unittest.main()
