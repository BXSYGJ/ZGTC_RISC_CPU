import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ila_analyze import header_for, read_capture, render_svg, summarize, validate_manifest


PROJECT = Path(__file__).resolve().parents[1]


class TargetIlaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.capture = self.root / "capture.csv"
        self.rows = [[str(index)] + ["0"] * 109 for index in range(1024)]
        self.rows[0][1 + 106] = "1"
        self.write_capture()
        self.manifest = {
            "Profile": "Target120", "Device": "PG2L200H-6FBB676", "ClockHz": 120000000,
            "SampleClockNet": "cpu_clk", "CaptureChannels": 109, "CaptureDepth": 1024,
            "TimingConstraintsMet": True,
            "Channel106Meaning": "fetch_complete",
        }
        artifacts = {
            "BitstreamSha256": "generate_bitstream/pds_soc_top.sbit", "FicSha256": "cpu.fic",
            "SourceAdfSha256": "source.adf", "SourceNetlistSha256": "netlist.v",
            "SourceManifestSha256": "source-manifest.json", "FirmwareSha256": "firmware.hex",
        }
        self.artifacts = artifacts
        for key, relative in artifacts.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if key == "FicSha256":
                data = (PROJECT / "scripts/cpu_ila_target120.fic.in").read_bytes()
            elif key == "SourceManifestSha256":
                data = json.dumps({"ClockHz": 120000000, "FirmwareSha256": hashlib.sha256(b"firmware.hex").hexdigest()}).encode()
            else:
                data = relative.encode()
            path.write_bytes(data)
            self.manifest[key] = hashlib.sha256(data).hexdigest()
        timing_path = self.root / "report_timing/pds_soc_top.rtr"
        timing_path.parent.mkdir()
        timing_path.write_text("Design Summary : All Constraints Met.\nclk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 8.333 {0 4.166} Generated (clk) 100\nclk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 120.0048 MHz 121.0000 MHz 8.333 8.264 0.069\n", encoding="utf-8")
        self.manifest_path = self.root / "manifest.json"
        self.save_manifest()

    def write_capture(self, profile="Target120"):
        with self.capture.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(header_for(profile))
            writer.writerows(self.rows)

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8-sig")

    def test_explicit_profile_and_clock(self):
        samples = read_capture(self.capture, "Target120")
        self.assertEqual(samples[0]["fetch_complete"], 1)
        self.assertNotIn("i_response", samples[0])
        report = summarize(samples, [], "Target120")
        self.assertEqual(report["clock_hz"], 120000000)
        self.assertAlmostEqual(report["window_us"], 1024 / 120)
        self.assertAlmostEqual(report["first_to_last_us"], 1023 / 120)
        self.assertNotIn("load_response_wait_cycles", report)
        self.assertIn("mem_load_sent_without_cache_response_cycles", report)
        image = render_svg(samples, "test", profile="Target120")
        self.assertIn("120 MHz", image)
        self.assertNotIn("27 MHz", image)
        self.assertNotIn("Physical JTAG", image)
        self.assertFalse(validate_manifest(self.manifest_path, "Target120")["hardware_origin_verified_by_analyzer"])

    def test_cross_profile_and_unknown_rejected(self):
        with self.assertRaises(ValueError):
            read_capture(self.capture)
        self.write_capture("Legacy27")
        with self.assertRaises(ValueError):
            read_capture(self.capture, "Target120")
        for operation in (
            lambda: header_for("unknown"), lambda: summarize([], [], "unknown"),
            lambda: render_svg([], "bad", profile="unknown"),
            lambda: validate_manifest(self.manifest_path, "unknown"),
        ):
            with self.assertRaises(ValueError):
                operation()

    def test_clock_and_configuration_mutations(self):
        changes = {"Profile": "Legacy27", "Device": "PG2L100H-6FBB676", "ClockHz": 27000000,
                   "SampleClockNet": "nt_clk", "CaptureChannels": 108, "CaptureDepth": 512,
                   "TimingConstraintsMet": 1}
        for key, value in changes.items():
            with self.subTest(key=key):
                old = self.manifest[key]
                self.manifest[key] = value
                self.save_manifest()
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, "Target120")
                self.manifest[key] = old
        self.save_manifest()

    def test_each_artifact_is_bound(self):
        for key, relative in self.artifacts.items():
            with self.subTest(key=key):
                path = self.root / relative
                data = path.read_bytes()
                path.write_bytes(data + b"changed")
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, "Target120")
                path.write_bytes(data)

    def test_rehashed_wrong_fic_rejected(self):
        path = self.root / "cpu.fic"
        original = path.read_text(encoding="utf-8-sig")
        changes = [
            ("clockChannel=cpu_clk", "clockChannel=nt_clk"),
            ("clockEdge=Rising", "clockEdge=Falling"),
            ("dataDepth=1024", "dataDepth=512"),
            ("triggerPortWidth<0>=109", "triggerPortWidth<0>=108"),
            ("=board/soc/core/fetch_complete", "=board/soc/i_rsp_valid"),
        ]
        for old, new in changes:
            with self.subTest(change=old):
                self.assertEqual(original.count(old), 1)
                path.write_text(original.replace(old, new), encoding="utf-8")
                self.manifest["FicSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.save_manifest()
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, "Target120")

    def test_temporal_transfer_still_checked(self):
        self.rows[0][1 + 97] = "1"
        self.rows[0][1 + 101] = "1"
        self.write_capture()
        with self.assertRaisesRegex(ValueError, "ID-to-EX"):
            read_capture(self.capture, "Target120")


    def test_original_timing_cannot_be_replaced_by_pass_flag(self):
        path = self.root / "report_timing/pds_soc_top.rtr"
        original = path.read_text()
        for old, new in (("All Constraints Met.", "Timing Constraints Not Met."), ("8.333", "37.037"), ("0.069", "-0.069"), ("Generated (clk) 100", "Generated (clk) 0")):
            with self.subTest(change=old):
                path.write_text(original.replace(old, new))
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, "Target120")


if __name__ == "__main__":
    unittest.main()
