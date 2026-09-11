from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class CarrySelectAluTests(unittest.TestCase):
    def simulate(self, variant="positive", randomized=False):
        source = (PROJECT / "rtl/rv32_alu.sv").read_text(encoding="utf-8")
        mutations = {
            "lost_carry": ("sum_low[16] ? sum_high_one : sum_high_zero", "sum_high_zero"),
            "lost_borrow": ("difference_low[16] ? difference_high_one : difference_high_zero", "difference_high_zero"),
            "wrong_borrow_bit": ("difference_low[16] ?", "difference_low[15] ?"),
            "wrong_borrow_sign": ("operand_a[31:16]-operand_b[31:16]-16'd1", "operand_a[31:16]-operand_b[31:16]+16'd1"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        top = "decode_alu_tb" if randomized else "alu_carry_select_tb"
        with tempfile.TemporaryDirectory(prefix="alu-carry-select-") as directory:
            work = Path(directory)
            rtl = work / "rv32_alu.sv"
            rtl.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", top, "-o", str(image),
                       str(rtl), str(PROJECT / "rtl/rv32_decode.sv"), str(PROJECT / "sim" / (top + ".sv"))]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], text=True, capture_output=True, timeout=30)

    def test_boundaries_and_all_original_operations(self):
        for randomized, expected in ((False, "PASS carry_select checks=640"),
                                     (True, "PASS decode_alu checks=13124")):
            with self.subTest(randomized=randomized):
                result = self.simulate(randomized=randomized)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)

    def test_carry_and_borrow_corruption_rejected(self):
        for variant in ("lost_carry", "lost_borrow", "wrong_borrow_bit", "wrong_borrow_sign"):
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL carry_select", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
