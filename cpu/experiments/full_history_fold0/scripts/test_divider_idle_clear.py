import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class DividerIdleControls(unittest.TestCase):
    def simulate(self, variant="positive"):
        source = (PROJECT / "experiments/idle_qualification/rv32_muldiv.sv").read_text(encoding="utf-8")
        replacements = {
            "qualified_clear": ("if(state==IDLE) remainder<=0;", "if(state==IDLE && req_valid && req_operand_b!=0) remainder<=0;"),
            "discard_partial_remainder": ("remainder<=subtract_divisor ? trial_remainder[31:0]-divisor : trial_remainder[31:0];", "remainder<=0;"),
            "early_finish": ("if(division_step==31)", "if(division_step==30)"),
        }
        if variant != "positive":
            before, after = replacements[variant]
            self.assertEqual(source.count(before), 1, "Mutation must match the isolated candidate RTL")
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="divider-idle-") as directory:
            root = Path(directory)
            rtl = root / "rv32_muldiv.sv"
            rtl.write_text(source, encoding="utf-8")
            image = root / "test.vvp"
            compilation = subprocess.run([
                "iverilog", "-g2012", "-s", "muldiv_tb", "-Pmuldiv_tb.CHECK_IDLE_CLEAR=1",
                "-o", str(image), str(rtl), str(PROJECT / "sim/muldiv_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=30)

    def test_arithmetic_idle_clear_cancel_and_response_latency(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("IDLE_CLEAR checks=", result.stdout)
        self.assertIn("PASS muldiv checks=12544", result.stdout)

    def test_negative_controls(self):
        failures = {
            "qualified_clear": "Idle remainder clear must not depend on request qualification",
            "discard_partial_remainder": "Muldiv op=",
            "early_finish": "Division response latency mismatch",
        }
        for variant, reason in failures.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
