import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class BtbAddressControls(unittest.TestCase):
    def simulate(self, variant, address_bits=16, index_bits=6):
        source = (PROJECT / "rtl" / "rv32_btb.sv").read_text(encoding="utf-8")
        mutations = {
            "fetch_alias": ("(fetch_pc >> ADDRESS_BITS)==0 && ", ""),
            "update_alias": ("(update_pc >> ADDRESS_BITS)==0 && ", ""),
            "target_alias": ("(update_target >> ADDRESS_BITS)==0 && ", ""),
            "target_shift": ("targets[fetch_index],2'b00", "2'b00,targets[fetch_index]"),
        }
        if variant != "positive":
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1, "Mutation anchor must match actual RTL")
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="btb-bounds-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "btb_bounds_tb",
                f"-Pbtb_bounds_tb.ADDRESS_BITS={address_bits}",
                f"-Pbtb_bounds_tb.INDEX_BITS={index_bits}",
                "-o", str(output), str(rtl), str(PROJECT / "sim" / "btb_bounds_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_supported_bounded_geometries(self):
        for address_bits, index_bits in ((10, 4), (14, 6), (16, 1), (16, 6), (16, 7), (16, 8)):
            with self.subTest(address_bits=address_bits, index_bits=index_bits):
                result = self.simulate("positive", address_bits, index_bits)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS btb_bounds checks=", result.stdout)

    def test_alias_and_target_corruption_are_rejected(self):
        expected = {
            "fetch_alias": "high fetch PC does not alias",
            "update_alias": "high update PC does not replace entry",
            "target_alias": "high update target does not replace entry",
            "target_shift": "first PC retained",
        }
        for variant, label in expected.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL btb_bounds " + label, result.stdout)
                self.assertNotIn("watchdog", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
