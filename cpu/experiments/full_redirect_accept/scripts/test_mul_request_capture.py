import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class MultiplyRequestControls(unittest.TestCase):
    def simulate(self, variant):
        source = (PROJECT / "rtl" / "rv32_muldiv.sv").read_text(encoding="utf-8")
        if variant == "unheld":
            anchor = "end else if(state==IDLE) begin"
            self.assertEqual(source.count(anchor), 1)
            source = source.replace(anchor, "end else begin")
        elif variant == "delayed":
            replacements = (
                ("IDLE=0,PRODUCT=2", "IDLE=0,MULTIPLY=1,PRODUCT=2"),
                ("state<=PRODUCT;", "state<=MULTIPLY;"),
                ("                PRODUCT: begin", "                MULTIPLY: state<=PRODUCT;" + chr(10) + "                PRODUCT: begin"),
            )
            for old, new in replacements:
                self.assertEqual(source.count(old), 1, "Mutation anchor must match actual RTL")
                source = source.replace(old, new)
        else:
            self.assertEqual(variant, "positive")
        with tempfile.TemporaryDirectory(prefix="mul-request-") as directory:
            work = Path(directory)
            rtl = work / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "muldiv_tb", "-o", str(output),
                str(rtl), str(PROJECT / "sim" / "muldiv_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_parallel_product_arithmetic_and_backpressure(self):
        result = self.simulate("positive")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS muldiv checks=12544", result.stdout)

    def test_old_extra_cycle_is_rejected(self):
        result = self.simulate("delayed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Product response latency mismatch op=0 waited=1", result.stdout)

    def test_product_overwrite_during_response_is_rejected(self):
        result = self.simulate("unheld")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Muldiv op=", result.stdout)
        self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
