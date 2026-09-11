import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class CacheLookupDataControls(unittest.TestCase):
    def simulate(self, variant="positive", readonly=0, fast_read=1, fast_write=1, overlap=1):
        source = (PROJECT / "rtl/rv32_cache.sv").read_text(encoding="utf-8")
        mutations = {
            "hit_gated_data": ("fast_lookup ? current_word : response_data", "fast_hit ? current_word : response_data"),
            "miss_response": ("assign rsp_valid=state==RESPONSE || fast_hit;", "assign rsp_valid=state==RESPONSE || fast_lookup;"),
            "wrong_way": ("wire [SET_BITS:0] hit_line=hit1 ? way1 : way0;", "wire [SET_BITS:0] hit_line=way0;"),
            "error_data": ("assign rsp_data=rsp_error ? 32'b0 : fast_lookup", "assign rsp_data=fast_lookup"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="cache-lookup-data-") as directory:
            work = Path(directory)
            rtl = work / "rv32_cache.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "cache_tb", "-o", str(output),
                       "-Pcache_tb.CHECK_LOOKUP_DATA=1", f"-Pcache_tb.READONLY={readonly}",
                       f"-Pcache_tb.FAST_READ_HIT={fast_read}", f"-Pcache_tb.FAST_WRITE_HIT={fast_write}",
                       f"-Pcache_tb.READ_OVERLAP={overlap}", str(rtl), str(PROJECT / "sim/cache_tb.sv")]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_modes_and_backpressure(self):
        for readonly, fast_read, fast_write, overlap in (
            (0, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 1, 1, 1),
            (1, 0, 0, 0), (1, 1, 0, 0), (1, 1, 0, 1),
        ):
            with self.subTest(readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap):
                result = self.simulate(readonly=readonly, fast_read=fast_read, fast_write=fast_write, overlap=overlap)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("LOOKUP_DATA hits=", result.stdout)
                self.assertIn("PASS cache", result.stdout)

    def test_negative_controls(self):
        expected = {"hit_gated_data": "lookup data independent of hit qualification",
                    "miss_response": "lookup miss never invents a response",
                    "wrong_way": "read data", "error_data": "valid response equals hit-qualified reference value"}
        for variant, message in expected.items():
            with self.subTest(variant=variant):
                result = self.simulate(variant)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
