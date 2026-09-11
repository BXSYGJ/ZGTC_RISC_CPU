import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class FastWriteControls(unittest.TestCase):
    def simulate(self, variant):
        source = (PROJECT / "rtl" / "rv32_cache.sv").read_text(encoding="utf-8")
        mutations = {
            "late": ("(FAST_WRITE_HIT!=0 && request_write && READ_ONLY==0)", "1'b0"),
            "new_value": ("fast_lookup ? current_word : response_data", "fast_lookup ? (request_write ? request_data : current_word) : response_data"),
        }
        if variant != "positive":
            old, new = mutations[variant]
            self.assertEqual(source.count(old), 1, "Mutation must match actual RTL exactly once")
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="fast-write-") as directory:
            work = Path(directory)
            rtl = work / "rv32_cache.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "cache_write_fast_tb", "-o", str(output), str(rtl),
                str(PROJECT / "sim" / "cache_tb.sv"), str(PROJECT / "sim" / "cache_write_fast_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_actual_fast_write_contract(self):
        result = self.simulate("positive")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS cache_write_fast checks=", result.stdout)

    def test_extra_response_cycle_is_rejected(self):
        result = self.simulate("late")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hot write responds on lookup cycle", result.stdout)
        self.assertNotIn("timeout", result.stdout.lower())

    def test_changed_write_response_value_is_rejected(self):
        result = self.simulate("new_value")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("response backpressure stability", result.stdout)
        self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
