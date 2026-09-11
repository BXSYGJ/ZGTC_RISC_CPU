from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class AddressCarryTests(unittest.TestCase):
    def simulate(self, variant="positive"):
        source = (PROJECT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        original = "    wire [31:0] effective_address=forwarded_a+ex_decode.immediate;"
        self.assertEqual(source.count(original), 1)
        if variant != "baseline":
            candidate = (PROJECT / "sim/address_carry_select_candidate.svh").read_text(encoding="utf-8").rstrip("\n")
            source = source.replace(original, candidate)
        mutations = {
            "lost_carry": ("address_low[16] ? address_high_one : address_high_zero", "address_high_zero"),
            "wrong_carry_bit": ("address_low[16] ?", "address_low[15] ?"),
            "wrong_high_carry": ("ex_decode.immediate[31:16]+16'd1", "ex_decode.immediate[31:16]-16'd1"),
            "cleared_address_low": ("address_high_zero,address_low[15:0]", "address_high_zero,address_low[15:2],2'b0"),
            "lost_immediate_sign": ("address_high_zero=forwarded_a[31:16]+ex_decode.immediate[31:16]", "address_high_zero=forwarded_a[31:16]"),
        }
        if variant not in ("positive", "baseline"):
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="address-carry-") as directory:
            work = Path(directory)
            core = work / "rv32_core.sv"
            core.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            dependencies = [PROJECT / "rtl" / name for name in (
                "rv32_machine.sv", "rv32_decode.sv", "rv32_alu.sv", "rv32_btb.sv", "rv32_muldiv.sv")]
            command = ["iverilog", "-g2012", "-s", "address_carry_select_tb", "-o", str(image),
                       str(core), *map(str, dependencies), str(PROJECT / "sim/address_carry_select_tb.sv")]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=30)

    def test_original_and_segmented_arithmetic(self):
        for variant in ("positive", "baseline"):
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS address_carry checks=20320", result.stdout)

    def test_arithmetic_alignment_and_sign_mutations(self):
        for variant in ("lost_carry", "wrong_carry_bit", "wrong_high_carry", "cleared_address_low", "lost_immediate_sign"):
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL address_carry", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
