import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parents[1] / "build/regfile-valid-fanout-stage"


class PrecomputeTests(unittest.TestCase):
    def run_bench(self, bench, mutation=None):
        source = (ROOT / "rtl/rv32_muldiv.sv").read_text(encoding="utf-8")
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="mul-precompute-") as temporary:
            work = Path(temporary)
            rtl = work / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            if bench.name == "muldiv_tb.sv":
                bench_text = bench.read_text(encoding="utf-8")
                self.assertEqual(bench_text.count("rv32_muldiv dut(.*);"), 1)
                bench_text = bench_text.replace("rv32_muldiv dut(.*);", "wire req_precomputed=0; rv32_muldiv #(.PRECOMPUTE(1)) dut(.*);")
                bench = work / "muldiv_tb.sv"
                bench.write_text(bench_text, encoding="utf-8")
            compiled = subprocess.run(["iverilog", "-g2012", "-s", bench.stem, "-o", str(image), str(rtl), str(bench)], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=120)

    def test_precompute_arithmetic_holding_cancel(self):
        result = self.run_bench(ROOT / "precompute_tb.sv")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS precompute", result.stdout)
        print(result.stdout.strip())

    def test_original_operations(self):
        result = self.run_bench(ROOT / "sim/muldiv_tb.sv")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutants(self):
        mutations = [
            ("req_precomputed && req_operation==0", "1'b0 && req_operation==0"),
            ("immediate_product ? product[31:0]", "immediate_product ? product[63:32]"),
            ("response_data<=product[31:0];", "response_data<=product[31:0]^32'd1;"),
            ("early_product || immediate_product) && !cancel", "early_product || immediate_product)"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.run_bench(ROOT / "precompute_tb.sv", mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL precompute", result.stdout + result.stderr)
                self.assertNotIn("watchdog", result.stdout + result.stderr)

    def test_exact_source_delta(self):
        manifest = json.loads((ROOT / "source-delta.json").read_text())
        for relative, expected in manifest["baseline"].items():
            before = (PARENT / relative).read_bytes()
            after = (ROOT / relative).read_bytes()
            self.assertEqual(hashlib.sha256(before).hexdigest().upper(), expected)
            self.assertEqual(hashlib.sha256(after).hexdigest().upper(), manifest["candidate"][relative])
            text = before.decode("utf-8")
            for old, new in manifest["edits"].get(relative, []):
                self.assertEqual(text.count(old), 1)
                text = text.replace(old, new)
            self.assertEqual(text, after.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
