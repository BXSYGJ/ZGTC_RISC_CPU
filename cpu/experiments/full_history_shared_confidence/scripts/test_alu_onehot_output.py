from hashlib import sha256
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = "47E2A54401C1F3AEEC1E4F840682DC353B51FA20757634A46ACC6134A513BBB6"


class OnehotOutputTests(unittest.TestCase):
    def simulate(self, variant="positive"):
        baseline_bytes = (PROJECT / "experiments/alu_kept_precompute/rv32_alu.sv").read_bytes()
        self.assertEqual(sha256(baseline_bytes).hexdigest().upper(), BASELINE_SHA256)
        baseline = baseline_bytes.decode("utf-8")
        candidate_name = "masked_or_rejected.sv" if variant == "masked_or_rejected" else "rv32_alu.sv"
        candidate_bytes = (PROJECT / "experiments/alu_onehot_output" / candidate_name).read_bytes()
        if variant == "masked_or_rejected":
            self.assertEqual(sha256(candidate_bytes).hexdigest().upper(),
                             "A1CFC2B71578929CD4FFF5C76DB5964202654ADBD4C0A31130F1917A70BE1582")
        candidate = candidate_bytes.decode("utf-8")
        mutations = {
            "wrong_left_select": ("operation_select[2]", "operation_select[6]"),
            "lost_arithmetic_sign": ("shift_arithmetic=$signed(operand_a)>>>operand_b[4:0]", "shift_arithmetic=operand_a>>operand_b[4:0]"),
            "upper_shift_bits": ("shift_left=operand_a<<operand_b[4:0]", "shift_left=operand_a<<operand_b"),
            "nonzero_invalid": ("default: decoded_operation=0", "default: decoded_operation=10'b0000000001"),
            "multiple_active": ("1: decoded_operation=10'b0000000010", "1: decoded_operation=10'b0000000011"),
            "disabled_lane_leak": ("operation_select[6]: result=shift_right", "1'b1: result=shift_right"),
        }
        if variant not in ("positive", "masked_or_rejected"):
            before, after = mutations[variant]
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="alu-onehot-output-") as directory:
            work = Path(directory)
            for name, source in (("baseline", baseline), ("candidate", candidate)):
                self.assertEqual(source.count("module rv32_alu ("), 1)
                (work / (name + ".sv")).write_text(source.replace("module rv32_alu (", "module rv32_alu_" + name + " ("), encoding="utf-8")
            image = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "alu_onehot_output_tb", "-o", str(image),
                                       str(work / "baseline.sv"), str(work / "candidate.sv"),
                                       str(PROJECT / "sim/alu_onehot_output_tb.sv")],
                                      text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], text=True, capture_output=True, timeout=30)

    def test_boundaries_shifts_random_and_four_state_opcodes(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS onehot_output checks=53440", result.stdout)

    def test_compiled_runtime_mutations_rejected(self):
        for variant in ("wrong_left_select", "lost_arithmetic_sign", "upper_shift_bits",
                        "nonzero_invalid", "multiple_active", "disabled_lane_leak"):
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL onehot_output", result.stdout + result.stderr)

    def test_rejected_masked_or_fixture_remains_detectable(self):
        result = self.simulate("masked_or_rejected")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL onehot_output op=0110 first=z0000000 second=00000010", result.stdout)
        self.assertIn("expected=0000z000 actual=0000x000", result.stdout)


if __name__ == "__main__":
    unittest.main()
