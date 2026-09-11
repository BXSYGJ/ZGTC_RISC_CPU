import csv
import tempfile
import unittest
from pathlib import Path
from ila_analyze import EXPECTED_HEADER, read_capture, read_symbols, summarize, render_svg


class IlaAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "capture.csv"
        self.rows = [[str(index)] + ["0"] * 109 for index in range(1024)]
        self.rows[0][1 + 8] = "1"
        for bit in (98, 100, 102):
            self.rows[0][1 + bit] = "1"
        self.rows[1][1 + 99] = "1"

    def write(self, header=None):
        with self.path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(EXPECTED_HEADER if header is None else header)
            writer.writerows(self.rows)

    def test_valid_mapping_and_summary(self):
        self.write()
        samples = read_capture(self.path)
        self.assertEqual(samples[0]["ex_pc"], 0x100)
        report = summarize(samples, [(0x100, 32, "algorithm")])
        self.assertEqual(report["wb_events"], 1)
        self.assertEqual(report["ex_fire_function_counts"], {"algorithm": 1})
        self.assertEqual(report["window_wb_per_cycle"], 1 / 1024)

    def test_header_and_truncation_rejected(self):
        self.write(EXPECTED_HEADER[::-1])
        with self.assertRaises(ValueError):
            read_capture(self.path)
        self.rows.pop()
        self.write()
        with self.assertRaises(ValueError):
            read_capture(self.path)

    def test_corrupt_rows_rejected(self):
        for column, value in ((0, "2"), (1, "x"), (99, "0")):
            with self.subTest(column=column):
                old = self.rows[0][column]
                self.rows[0][column] = value
                self.write()
                with self.assertRaises(ValueError):
                    read_capture(self.path)
                self.rows[0][column] = old

    def test_temporal_mapping_rejected(self):
        self.rows[1][1 + 99] = "0"
        self.write()
        with self.assertRaises(ValueError):
            read_capture(self.path)
        self.rows[1][1 + 99] = "1"
        self.rows[0][1 + 97] = "1"
        self.rows[0][1 + 101] = "1"
        self.write()
        with self.assertRaises(ValueError):
            read_capture(self.path)

    def test_symbols_and_svg(self):
        symbols = Path(self.directory.name) / "symbols.txt"
        symbols.write_text("00000100 00000020 T algorithm\n00000300 R data\n", encoding="utf-8")
        self.assertEqual(read_symbols(symbols), [(256, 32, "algorithm")])
        self.write()
        samples = read_capture(self.path)
        self.assertIn("&lt;test&gt;", render_svg(samples, "<test>"))
        with self.assertRaises(ValueError):
            render_svg(samples, "bad", start=1020, length=128)


if __name__ == "__main__":
    unittest.main()
