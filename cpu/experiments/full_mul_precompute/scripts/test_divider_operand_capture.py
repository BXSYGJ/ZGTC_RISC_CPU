import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class DividerOperandCaptureControls(unittest.TestCase):
    def simulate(self, variant="positive", monitor=1):
        source = (PROJECT / "rtl/rv32_muldiv.sv").read_text(encoding="utf-8")
        replacements = {
            "qualified_capture": ("            if(state==IDLE) begin", "            if(state==IDLE && req_valid) begin"),
            "overwrite_busy": ("            if(state==IDLE) begin", "            if(1'b1) begin"),
            "wrong_unsigned_magnitude": ("divisor<=negative_b ? -req_operand_b : req_operand_b;", "divisor<=req_operand_b[31] ? -req_operand_b : req_operand_b;"),
            "invent_request": ("IDLE: if(req_valid) begin", "IDLE: begin"),
        }
        if variant != "positive":
            before, after = replacements[variant]
            self.assertEqual(source.count(before), 1, "Mutation must match current divider capture RTL")
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="divider-capture-") as directory:
            root = Path(directory)
            rtl = root / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            image = root / "test.vvp"
            compilation = subprocess.run([
                "iverilog", "-g2012", "-s", "muldiv_tb", f"-Pmuldiv_tb.CHECK_IDLE_CAPTURE={monitor}",
                "-o", str(image), str(rtl), str(PROJECT / "sim/muldiv_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=30)

    def test_idle_capture_arithmetic_hold_and_exact_response_latency(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IDLE_CAPTURE samples=", result.stdout)
        self.assertIn("PASS muldiv checks=12544", result.stdout)

    def test_negative_controls(self):
        failures = {
            "qualified_capture": (1, "Idle divider operand capture must be independent of request qualification"),
            "overwrite_busy": (1, "Busy divider operands must not follow changing request inputs"),
            "wrong_unsigned_magnitude": (0, "Muldiv op="),
            "invent_request": (1, "Unit not idle before request"),
        }
        for variant, (monitor, reason) in failures.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant, monitor)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()

