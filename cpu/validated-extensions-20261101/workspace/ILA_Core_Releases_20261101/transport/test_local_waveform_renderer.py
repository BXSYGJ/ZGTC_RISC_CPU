"""Local-only tests. Every generated sample is an explicitly synthetic fixture."""
from decimal import Decimal
from pathlib import Path
import copy
import csv
import json
import tempfile
import unittest

import render_ila_waveforms as renderer


def synthetic_rows():
    result = []
    for sample in range(1024):
        pc = 0x942 if sample == 256 else 0x944 + 2 * (sample % 32)
        result.append([(pc >> bit) & 1 for bit in range(32)] +
                      [1, 1, 1, 1, 1, 1, 1, 0, sample % 2, 1, int(sample == 256)])
    return result


def write_synthetic_vcd(path, *, unknown_sample=None, period_ps=10000):
    rows = synthetic_rows()
    variables = [("cpu_clk", 1), ("ex_pc", 32)] + [(name, 1) for name in renderer.LOCAL_SEMANTICS]
    variables += [("cyclecounter", 64), ("Trigger", 1)]
    header = ["$comment EXPLICIT SYNTHETIC OFFLINE TEST FIXTURE $end", "$timescale 1ps $end",
              "$scope module SYNTHETIC_FIXTURE $end"]
    codes = {name: f"v{index}" for index, (name, _) in enumerate(variables)}
    header += [f"$var wire {width} {codes[name]} {name} $end" for name, width in variables]
    header += ["$upscope $end", "$enddefinitions $end", "#0", "0" + codes["cpu_clk"]]
    lines = header
    for sample, row in enumerate(rows):
        timestamp = sample * period_ps + period_ps // 2
        lines += [f"#{timestamp}", "1" + codes["cpu_clk"]]
        pc = sum(row[bit] << bit for bit in range(32))
        lines += [f"b{pc:032b} {codes['ex_pc']}"]
        for index, name in enumerate(renderer.LOCAL_SEMANTICS):
            bit = "x" if sample == unknown_sample and name == "ex_valid" else str(row[32 + index])
            lines += [bit + codes[name]]
        lines += [f"b{sample + 500:064b} {codes['cyclecounter']}", str(row[42]) + codes["Trigger"],
                  f"#{timestamp + period_ps // 2}", "0" + codes["cpu_clk"]]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


class LocalRendererTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="SYNTHETIC_renderer_fixture_")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_settled_timestamp_groups_match_every_synthetic_bit(self):
        path = self.root / "SYNTHETIC.vcd"
        expected = write_synthetic_vcd(path)
        rows, times, cycles, predicates, metadata = renderer.read_recorded_vcd(path)
        self.assertEqual(rows, [row[:42] for row in expected])
        self.assertEqual(times, [Decimal(sample * 10000 + 5000) for sample in range(1024)])
        self.assertEqual(cycles, list(range(500, 1524)))
        self.assertEqual(predicates, [row[42] for row in expected])
        self.assertEqual(metadata["rising_edge_period_ps"], "10000")

    def test_unknown_sample_is_rejected_without_fill(self):
        path = self.root / "SYNTHETIC_unknown.vcd"
        write_synthetic_vcd(path, unknown_sample=43)
        with self.assertRaisesRegex(renderer.CaptureError, "unknown or absent"):
            renderer.read_recorded_vcd(path)

    def test_missing_edge_is_rejected(self):
        path = self.root / "SYNTHETIC_missing_edge.vcd"
        write_synthetic_vcd(path)
        text = path.read_text(encoding="utf-8").replace("#1005000\n1v0", "#1005000\n0v0")
        path.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(renderer.CaptureError, "1023 rising-edge"):
            renderer.read_recorded_vcd(path)

    def test_trigger_annotation_and_pipeline_validity(self):
        rows = synthetic_rows()
        checks = renderer.validate_pipeline(rows, 0x942)
        self.assertEqual(checks["trigger_matching_indices"], [256])
        self.assertEqual(checks["wb_events"], 1024)
        self.assertFalse(checks["frontend_fire_to_next_IF_valid_asserted"])
        rows[256][34] = 0
        with self.assertRaisesRegex(renderer.CaptureError, "valid"):
            renderer.validate_pipeline(rows, 0x942)

    def test_synthetic_plot_is_explicitly_labeled(self):
        rows = synthetic_rows()
        receipt = {"variant": "SYNTHETIC TEST", "configured_clock_hz": 155250000,
                   "checks": renderer.validate_pipeline(rows, 0x942),
                   "alignment": {"first_aligned_trigger_index": 256}, "raw_sha256": "0" * 64}
        symbols = [{"name": "SYNTHETIC_core_bench_list", "address": 0x942, "size": 0x500}]
        result = renderer.plot_window(receipt, rows, symbols, {"kind": "SYNTHETIC_OFFLINE_FIXTURE"},
                                      self.root, start=248, length=32, stem="SYNTHETIC_zoom")
        svg = Path(result["svg"]).read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC OFFLINE FIXTURE", svg)
        self.assertIn("synthetic test fixture", svg)
        self.assertNotIn("LOCAL RTL SIMULATION", svg)
        from PIL import Image
        with Image.open(result["png"]) as image:
            self.assertEqual(image.size, (3240, 1548))
            image.verify()


class ActualRecordingTamperTests(unittest.TestCase):
    """Mutate temporary copies of actual recordings; never render them as data."""
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.original = root / "Original_155250" / "waveforms" / "WAVEFORM_MANIFEST.json"
        self.temporary = tempfile.TemporaryDirectory(prefix="TAMPER_TEST_actual_recording_copy_")
        self.root = Path(self.temporary.name)
        self.manifest = copy.deepcopy(renderer.read_json(self.original))

    def tearDown(self):
        self.temporary.cleanup()

    def _copied_window(self):
        window = self.manifest["windows"][0]
        for key in ("csv", "vcd", "raw_csv", "decoded_csv"):
            original = renderer.bound_path(self.original, window[key])
            path = self.root / original.name
            path.write_bytes(original.read_bytes())
            window[key] = str(path)
        return window

    def _save_manifest(self):
        path = self.root / "COPIED_MANIFEST_FOR_TAMPER_TEST.json"
        renderer.write_json(path, self.manifest)
        return path

    def test_changed_native_csv_bit_rejected_even_when_hash_updated(self):
        window = self._copied_window()
        path = Path(window["csv"])
        with path.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.reader(stream))
        records[20][1] = str(1 - int(records[20][1]))
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(records)
        window["csv_sha256"] = renderer.sha256(path)
        with self.assertRaisesRegex(renderer.CaptureError, "CSV probe bits differ"):
            renderer.verify_local_window(self._save_manifest(), window)

    def test_changed_packed_observation_rejected_even_when_hash_updated(self):
        window = self._copied_window()
        path = Path(window["raw_csv"])
        with path.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.reader(stream))
        records[20][2] = str(int(records[20][2]) ^ 1)
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(records)
        window["raw_csv_sha256"] = renderer.sha256(path)
        with self.assertRaisesRegex(renderer.CaptureError, "packed RTL observation differs"):
            renderer.verify_local_window(self._save_manifest(), window)

    def test_hardware_relabel_is_rejected(self):
        window = self._copied_window()
        self.manifest["origin"] = "HARDWARE"
        with self.assertRaisesRegex(renderer.CaptureError, "LOCAL RTL SIMULATION"):
            renderer.verify_local_window(self._save_manifest(), window)


if __name__ == "__main__":
    unittest.main()
