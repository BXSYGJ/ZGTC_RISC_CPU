import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = 'c4f0ef80e634f153f5bf1cb2b0f9bb314432333bf9dc93e1a8e9f6e1c2cc2346'


class FetchPcPrecomputeTests(unittest.TestCase):
    def simulate(self, variant, predictor, mutation=None):
        baseline = (PROJECT / 'rtl/rv32_core.sv').read_bytes()
        self.assertEqual(hashlib.sha256(baseline).hexdigest(), BASELINE_SHA256)
        source = baseline.decode() if variant == 'baseline' else (PROJECT / f'experiments/fetch_pc_precompute/rv32_core_{variant}.sv').read_text()
        if variant != 'baseline':
            start = source.index('    (* syn_keep=1 *) wire [31:0] sequential_fetch_pc')
            end = source.index('    wire csr_write_intent', start)
            restored = (source[:start] + source[end:]).replace(' : sequential_fetch_pc;', " : next_pc+32'd4;")
            self.assertEqual(restored, baseline.decode())
        if mutation is not None:
            before, after, count = mutation
            self.assertEqual(source.count(before), count)
            source = source.replace(before, after)
        bench = (PROJECT / 'sim/fetch_pc_precompute_tb.sv').read_text()
        if variant == 'baseline':
            bench = bench.replace('                if(dut.sequential_fetch_pc!==sequential) $fatal(1,"FAIL fetch_pc_precompute increment");', '')
        with tempfile.TemporaryDirectory(prefix='fetch-pc-precompute-') as directory:
            work = Path(directory)
            core = work / 'rv32_core.sv'
            core.write_text(source, encoding='utf-8')
            testbench = work / 'testbench.sv'
            testbench.write_text(bench, encoding='utf-8')
            image = work / 'test.vvp'
            dependencies = [PROJECT / 'rtl' / name for name in (
                'rv32_machine.sv', 'rv32_decode.sv', 'rv32_alu.sv', 'rv32_btb.sv', 'rv32_muldiv.sv')]
            command = ['iverilog', '-g2012', '-s', 'fetch_pc_precompute_tb', '-o', str(image),
                       f'-Pfetch_pc_precompute_tb.PREDICTOR={predictor}', str(core),
                       *map(str, dependencies), str(testbench)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(['vvp', str(image)], capture_output=True, text=True, timeout=30)

    def test_baseline_and_candidates(self):
        for variant in ('baseline', 'kept', 'grouped'):
            for predictor in (0, 1):
                with self.subTest(variant=variant, predictor=predictor):
                    result = self.simulate(variant, predictor)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f'PASS fetch_pc_precompute checks=11504 predictor={predictor}', result.stdout)
                    print(f'PASS variant={variant} predictor={predictor} checks=11504')

    def test_compiled_semantic_faults_rejected(self):
        common = [
            ('prediction_hit && predicted_taken', 'predicted_taken', 2),
            ('? predicted_target : sequential_fetch_pc;', '? sequential_fetch_pc : sequential_fetch_pc;', 2),
            ('fetch_prediction<=(ENABLE_PREDICTOR!=0 && prediction_hit && predicted_taken) ? predicted_target : sequential_fetch_pc;',
             "fetch_prediction<=32'hdeadbeef;", 1),
        ]
        for variant in ('kept', 'grouped'):
            mutations = common.copy()
            if variant == 'kept':
                mutations += [("sequential_fetch_pc=next_pc+32'd4;", "sequential_fetch_pc=(next_pc+32'd4) & 32'hfffffffc;", 1),
                              ("sequential_fetch_pc=next_pc+32'd4;", "sequential_fetch_pc=next_pc+32'd8;", 1)]
            else:
                mutations += [("sequential_fetch_pc[1:0]=next_pc[1:0];", "sequential_fetch_pc[1:0]=2'b0;", 1),
                              ("{7'b0,&next_pc[9:2]}", "8'b0", 1),
                              ('&next_pc[25:2]', '&next_pc[24:2]', 1)]
            for mutation in mutations:
                with self.subTest(variant=variant, mutation=mutation):
                    result = self.simulate(variant, 1, mutation)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('FAIL fetch_pc_precompute', result.stdout + result.stderr)
                    self.assertNotIn('PASS fetch_pc_precompute', result.stdout)
                    print(f'PASS compiled rejection variant={variant} mutation={mutation[0]}')


if __name__ == '__main__':
    unittest.main()

