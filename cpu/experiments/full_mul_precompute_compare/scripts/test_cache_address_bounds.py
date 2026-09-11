import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class CacheAddressControls(unittest.TestCase):
    def simulate(self, variant, address_bits=10):
        source = (PROJECT / "rtl" / "rv32_cache.sv").read_text(encoding="utf-8")
        if variant == "alias":
            old, new = "(req_address >> ADDRESS_BITS)!=0 || ", ""
        elif variant == "writeback":
            old, new = "tags[scan_line],scan_line[SET_BITS-1:0]", "{TAG_BITS{1'b0}},scan_line[SET_BITS-1:0]"
        else:
            self.assertEqual(variant, "positive")
            old = new = None
        if old is not None:
            self.assertEqual(source.count(old), 1, "Mutation anchor must match actual RTL")
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="cache-bounds-") as directory:
            work = Path(directory)
            rtl = work / "rv32_cache.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "cache_bounds_tb",
                f"-Pcache_bounds_tb.ADDRESS_BITS={address_bits}",
                "-o", str(output), str(rtl), str(PROJECT / "rtl" / "rv32_burst_ram.sv"),
                str(PROJECT / "sim" / "cache_bounds_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_physical_bounds_and_dirty_flush(self):
        for bits in (10, 14, 16):
            with self.subTest(address_bits=bits):
                result = self.simulate("positive", bits)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS cache_bounds checks=", result.stdout)

    def test_dropping_high_address_guard_is_rejected(self):
        result = self.simulate("alias")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL cache_bounds physical address response error", result.stdout)
        self.assertNotIn("watchdog", result.stdout.lower())

    def test_truncated_writeback_tag_is_rejected(self):
        result = self.simulate("writeback")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FAIL cache_bounds first and last dirty lines write back to full addresses", result.stdout)
        self.assertNotIn("watchdog", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
