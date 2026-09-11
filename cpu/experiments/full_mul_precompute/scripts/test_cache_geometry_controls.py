import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class CacheGeometryControls(unittest.TestCase):
    def simulate(self, mutation=None):
        with tempfile.TemporaryDirectory(prefix="cache-geometry-") as directory:
            work = Path(directory)
            sources = sorted((PROJECT / "rtl").glob("*.sv"))
            if mutation is not None:
                filename, old, new = mutation
                original = PROJECT / "rtl" / filename
                text = original.read_text(encoding="utf-8")
                self.assertEqual(text.count(old), 1, "Mutation must match actual RTL exactly once")
                changed = work / filename
                changed.write_text(text.replace(old, new), encoding="utf-8")
                sources = [changed if source == original else source for source in sources]
            output = work / "test.vvp"
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "cache_geometry_tb", "-o", str(output),
                *map(str, sources), str(PROJECT / "sim" / "cache_geometry_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_actual_geometry_and_configuration(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS cache_geometry checks=6", result.stdout)

    def test_wrong_capacity_or_identity_is_rejected(self):
        selector = "cache_index==0 && ICACHE_SET_BITS!=0 ? ICACHE_SET_BITS : CACHE_SET_BITS"
        mutations = [
            ("rv32_memory_system.sv", selector, "CACHE_SET_BITS"),
            ("rv32_memory_system.sv", selector, selector.replace("cache_index==0", "cache_index==1")),
            ("rv32_soc.sv", ".ICACHE_SET_BITS(ICACHE_SET_BITS)", ".ICACHE_SET_BITS(0)"),
            ("rv32_soc.sv", "? ICACHE_SET_BITS : 0)<<12", "? ICACHE_SET_BITS : 0)<<11"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stdout, r"cache geometry (physical widths|MMIO configuration)")
                self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
