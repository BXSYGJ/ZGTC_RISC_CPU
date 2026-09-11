import tempfile
import unittest
from pathlib import Path

from audit_fetch_pipeline import OUTPUT, read_capture, read_symbols, summarize, validate_mem_transfers

PROFILE = "FetchCommit153000MinimalRtl"


class PipelineCaptureTests(unittest.TestCase):
    def setUp(self):
        self.path = OUTPUT / "core_bench_matrix.csv"
        self.samples = read_capture(self.path, PROFILE)

    def test_actual_three_algorithm_windows(self):
        symbols = read_symbols(OUTPUT / "symbols.txt")
        for name in ("core_bench_list", "core_bench_matrix", "core_bench_state"):
            samples = read_capture(OUTPUT / (name + ".csv"), PROFILE)
            validate_mem_transfers(samples)
            report = summarize(samples, symbols, PROFILE)
            with self.subTest(name=name):
                self.assertEqual(report["samples"], 1024)
                self.assertEqual(report["clock_hz"], 153000000)
                self.assertEqual(report["temporal_pairs_checked"], 1023)
                self.assertTrue(samples[0]["ex_fire"])
                self.assertIn(samples[0]["ex_pc"], [address for address, size, symbol in symbols if symbol == name])

    def test_mem_fire_without_valid_rejected(self):
        sample = next(sample for sample in self.samples if sample["mem_fire"])
        sample["mem_valid"] = 0
        with self.assertRaisesRegex(ValueError, "MEM fire"):
            validate_mem_transfers(self.samples)

    def test_wb_without_prior_commit_rejected(self):
        index = next(index for index in range(1, len(self.samples)) if self.samples[index]["wb_valid"])
        self.samples[index - 1]["mem_fire"] = 0
        with self.assertRaisesRegex(ValueError, "preceding MEM fire"):
            validate_mem_transfers(self.samples)

    def test_corrupt_width_index_and_sample_count_rejected(self):
        lines = self.path.read_text(encoding="utf-8").splitlines()
        corruptions = [lines[:-1], [lines[0] + ",extra", *lines[1:]], [lines[0], lines[1].replace("0,", "9,", 1), *lines[2:]]]
        with tempfile.TemporaryDirectory(prefix="pipeline-controls-") as temporary:
            path = Path(temporary) / "capture.csv"
            for changed in corruptions:
                path.write_text("\n".join(changed) + "\n", encoding="utf-8")
                with self.subTest(first=changed[1][:12], count=len(changed)), self.assertRaises(ValueError):
                    read_capture(path, PROFILE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
