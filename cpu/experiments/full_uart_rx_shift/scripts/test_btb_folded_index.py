import itertools
from pathlib import Path
import subprocess
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class FoldedBtbTests(unittest.TestCase):
    def simulate(self, bits=8, address_bits=16, enabled=1, rotate=0, variant="positive"):
        source = (PROJECT / "rtl/rv32_btb.sv").read_text(encoding="utf-8")
        mutations = {
            "fetch_unfolded": ("HASH_INDEX!=0 ? fetch_fold", "1'b0 ? fetch_fold"),
            "update_unfolded": ("HASH_INDEX!=0 ? update_fold", "1'b0 ? update_fold"),
            "tag_ignored": (" && tags[fetch_index]==fetch_tag", ""),
        }
        if variant != "positive":
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="btb-folded-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "btb_tb", "-o", str(image),
                       f"-Pbtb_tb.INDEX_BITS={bits}", f"-Pbtb_tb.ADDRESS_BITS={address_bits}",
                       f"-Pbtb_tb.HASH_INDEX={enabled}", f"-Pbtb_tb.HASH_ROTATE={rotate}",
                       str(rtl), str(PROJECT / "sim/btb_tb.sv")]
            compiled = subprocess.run(command, text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], text=True, capture_output=True, timeout=30)

    def test_geometries_modes_and_rotations(self):
        for bits, address_bits, enabled, rotate in itertools.product((1, 4, 6, 7, 8), (16, 32), (0, 1), range(8)):
            with self.subTest(bits=bits, address_bits=address_bits, enabled=enabled, rotate=rotate):
                result = self.simulate(bits, address_bits, enabled, rotate)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS btb checks=", result.stdout)

    def test_asymmetric_hash_and_missing_tag_rejected(self):
        for variant in ("fetch_unfolded", "update_unfolded", "tag_ignored"):
            for rotate in range(8):
                with self.subTest(variant=variant, rotate=rotate):
                    result = self.simulate(rotate=rotate, variant=variant)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("FAIL BTB", result.stdout + result.stderr)
                    self.assertNotIn("watchdog", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
