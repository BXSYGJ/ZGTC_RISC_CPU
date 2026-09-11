import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class MemoryOverlapControls(unittest.TestCase):
    def simulate(self, overlap, fast, mutate=False):
        memory = PROJECT / "rtl" / "rv32_memory_system.sv"
        with tempfile.TemporaryDirectory(prefix="data-overlap-") as directory:
            work = Path(directory)
            if mutate:
                source = memory.read_text(encoding="utf-8")
                clear = "            if(d_rsp_valid && d_rsp_ready) data_active<=0;"
                accept = "            if(d_req_valid && d_req_ready) begin data_active<=1; data_mmio<=request_mmio; end"
                original = clear + "\n" + accept
                self.assertEqual(source.count(original), 1, "Mutation must match the actual owner priority")
                memory = work / "rv32_memory_system.sv"
                memory.write_text(source.replace(original, accept + "\n" + clear), encoding="utf-8")
            sources = [PROJECT / "rtl" / name for name in (
                "rv32_cache.sv", "rv32_uncached.sv", "rv32_burst_arbiter.sv", "rv32_burst_ram.sv",
            )]
            output = work / "test.vvp"
            compile_result = subprocess.run([
                "iverilog", "-g2012", "-s", "memory_overlap_tb",
                f"-Pmemory_overlap_tb.DATA_OVERLAP={overlap}",
                f"-Pmemory_overlap_tb.FAST_DCACHE_READ={fast}",
                "-o", str(output), str(memory), *map(str, sources),
                str(PROJECT / "sim" / "memory_overlap_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_enabled_overlap(self):
        for fast in (0, 1):
            with self.subTest(fast=fast):
                result = self.simulate(1, fast)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS memory_overlap checks=", result.stdout)
                self.assertIn("handovers=4", result.stdout)

    def test_disabled_overlap_rejected_at_handover(self):
        for fast in (0, 1):
            with self.subTest(fast=fast):
                result = self.simulate(0, fast)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL memory_overlap old response and next request overlap", result.stdout)
                self.assertNotIn("watchdog", result.stdout.lower())

    def test_lost_owner_mutation_rejected(self):
        for fast in (0, 1):
            with self.subTest(fast=fast):
                result = self.simulate(1, fast, mutate=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL memory_overlap request handover preserves active owner", result.stdout)
                self.assertNotIn("watchdog", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
