import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class MmioPayloadControls(unittest.TestCase):
    def simulate(self, cache=1, overlap=1, fast=1, variant="positive"):
        source = (PROJECT / "experiments/idle_qualification/rv32_memory_system.sv").read_text(encoding="utf-8")
        replacements = {
            "qualified_payload": ("if(!mmio_request_pending) begin", "if(d_req_valid && d_req_ready && request_mmio) begin"),
            "overwrite_pending": ("if(!mmio_request_pending) begin", "if(1'b1) begin"),
            "invent_request": ("if(d_req_valid && d_req_ready && request_mmio) mmio_request_pending<=1;", "if(request_mmio && !mmio_request_pending) mmio_request_pending<=1;"),
            "wrong_strobe": ("mmio_request_strobe<=d_req_strobe;", "mmio_request_strobe<=4'b1111;"),
        }
        if variant != "positive":
            before, after = replacements[variant]
            self.assertEqual(source.count(before), 1, "Mutation must match the isolated candidate RTL")
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="mmio-payload-") as directory:
            root = Path(directory)
            memory = root / "rv32_memory_system.sv"
            memory.write_text(source, encoding="utf-8")
            image = root / "test.vvp"
            sources = [PROJECT / "rtl" / name for name in (
                "rv32_cache.sv", "rv32_uncached.sv", "rv32_burst_arbiter.sv", "rv32_burst_ram.sv")]
            compilation = subprocess.run([
                "iverilog", "-g2012", "-s", "mmio_payload_tb", f"-Pmmio_payload_tb.ENABLE_CACHE={cache}",
                f"-Pmmio_payload_tb.DATA_OVERLAP={overlap}", f"-Pmmio_payload_tb.FAST_CACHE={fast}",
                "-o", str(image), str(memory), *map(str, sources), str(PROJECT / "sim/mmio_payload_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compilation.returncode, 0, compilation.stdout + compilation.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=30)

    def test_mixed_requests_with_poison_backpressure_and_reset(self):
        for cache in (0, 1):
            for overlap in (0, 1):
                for fast in (0, 1):
                    with self.subTest(cache=cache, overlap=overlap, fast=fast):
                        result = self.simulate(cache, overlap, fast)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("PASS mmio_payload checks=", result.stdout)
                        self.assertIn("requests=72 mmio=48 cache=24", result.stdout)

    def test_negative_controls(self):
        failures = {
            "qualified_payload": "idle payload sampling is independent of request qualification",
            "overwrite_pending": "pending payload cannot follow changing CPU pins",
            "invent_request": "MMIO valid requires an accepted MMIO owner",
            "wrong_strobe": "idle payload sampling is independent of request qualification",
        }
        for variant, reason in failures.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant=variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stdout)
                self.assertNotIn("watchdog", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
