import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class FastLowMultiplyTests(unittest.TestCase):
    def simulate(self, variant="positive", exhaustive=False):
        source = (PROJECT / "experiments/fast_low_mul/rv32_muldiv.sv").read_text(encoding="utf-8")
        mutations = {
            "delayed": ("wire immediate_product=FAST_LOW_MUL!=0", "wire immediate_product=1'b0 && FAST_LOW_MUL!=0"),
            "wrong_cross": ("request_product_low_low+{request_product_cross,16'b0}", "request_product_low_low"),
            "duplicate": ("if(!rsp_ready) begin", "if(1'b1) begin"),
            "unheld": ("response_data<=request_product_low;", "response_data<=32'b0;"),
            "uncanceled": ("early_product || immediate_product) && !cancel", "early_product || immediate_product)"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        top = "muldiv_tb" if exhaustive else "fast_low_mul_tb"
        with tempfile.TemporaryDirectory(prefix="fast-low-mul-") as directory:
            work = Path(directory)
            rtl = work / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", top, "-o", str(output)]
            command.extend([str(rtl), str(PROJECT / "sim" / (top + ".sv"))])
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_immediate_back_to_back_and_held(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS fast_low_mul checks=", result.stdout)

    def test_all_operations_arithmetic_backpressure_and_cancel(self):
        result = self.simulate(exhaustive=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS muldiv checks=12544", result.stdout)

    def test_mutations_are_observable(self):
        expected = {"delayed": "Immediate low product mismatch", "wrong_cross": "Immediate low product mismatch",
                    "duplicate": "Consumed low product duplicated", "unheld": "Held low product changed",
                    "uncanceled": "Immediate cancellation leaked handshake"}
        for variant, message in expected.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
