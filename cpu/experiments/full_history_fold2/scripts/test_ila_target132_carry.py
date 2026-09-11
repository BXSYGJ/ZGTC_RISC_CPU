import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ila_analyze import header_for, read_capture, render_svg, summarize, validate_manifest


PROJECT = Path(__file__).resolve().parents[1]


class CarryIlaTests(unittest.TestCase):
    profile = "Target132Carry"
    source_lock = "ila_target132_carry_sources.json"
    fic_template = "cpu_ila_target132_carry.fic.in"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.capture = self.root / "capture.csv"
        self.rows = [[str(index)] + ["0"] * 109 for index in range(1024)]
        self.rows[0][1 + 99] = "1"
        self.rows[0][1 + 103] = "1"
        self.rows[0][1 + 104] = "1"
        self.rows[1][1 + 99] = "1"
        self.rows[1][1 + 106] = "1"
        self.rows[1][1 + 107] = "1"
        self.rows[2][1 + 100] = "1"
        self.write_capture()
        self.manifest = {
            "Profile": self.profile, "Device": "PG2L200H-6FBB676", "ClockHz": 132000000,
            "SampleClockNet": "cpu_clk", "CaptureChannels": 109, "CaptureDepth": 1024,
            "TimingConstraintsMet": True, "Channel106Meaning": "fetch_complete",
            "Channel107Meaning": "mem_fire",
        }
        self.source = {
            "Device": "PG2L200H-6FBB676", "ClockHz": 132000000, "TimingConstraintsMet": True,
            "CacheEnabled": 1, "Predictor": 1, "UartProfile": "RemoteLab", "UartBaud": 115200,
            "EnableM": 1, "FetchOverlap": 1, "FastDCacheRead": 1, "FastDCacheWrite": 1,
            "ICacheSetBits": 8, "CacheSetBits": 6, "EarlyDRequest": 1, "BtbIndexBits": 8,
            "DataOverlap": 1, "FastICacheHit": 1, "LoadUseBubble": 0,
            "FirmwareSha256": hashlib.sha256(b"firmware.hex").hexdigest(),
            "SourceSnapshot": {"Schema": 1, "Files": json.loads(
                (PROJECT / "scripts" / self.source_lock).read_text(encoding="utf-8-sig"))},
        }
        self.artifacts = {
            "BitstreamSha256": "generate_bitstream/pds_soc_top.sbit", "FicSha256": "cpu.fic",
            "SourceAdfSha256": "source.adf", "SourceNetlistSha256": "netlist.v",
            "SourceManifestSha256": "source-manifest.json", "FirmwareSha256": "firmware.hex",
        }
        for key, relative in self.artifacts.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if key == "FicSha256":
                data = (PROJECT / "scripts" / self.fic_template).read_bytes()
            elif key == "SourceManifestSha256":
                data = json.dumps(self.source).encode("utf-8")
            else:
                data = relative.encode("utf-8")
            path.write_bytes(data)
            self.manifest[key] = hashlib.sha256(data).hexdigest()
        self.timing = self.root / "report_timing/pds_soc_top.rtr"
        self.timing.parent.mkdir()
        self.timing.write_text(
            "Design Summary : All Constraints Met.\n"
            "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 7.575 {0 3.787} Generated (clk) 100\n"
            "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 132.0132 MHz 133.833 MHz 7.575 7.472 0.103\n",
            encoding="utf-8")
        self.manifest_path = self.root / "manifest.json"
        self.save_manifest()

    def write_capture(self, profile=None):
        profile = self.profile if profile is None else profile
        with self.capture.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(header_for(profile))
            writer.writerows(self.rows)

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8-sig")

    def rehash(self, key):
        self.manifest[key] = hashlib.sha256((self.root / self.artifacts[key]).read_bytes()).hexdigest()
        self.save_manifest()

    def test_profile_semantics_and_rendering(self):
        samples = read_capture(self.capture, self.profile)
        self.assertEqual(samples[1]["mem_fire"], 1)
        self.assertEqual(samples[1]["fetch_complete"], 1)
        self.assertNotIn("d_response", samples[1])
        self.assertNotIn("i_response", samples[1])
        report = summarize(samples, [], self.profile)
        self.assertEqual(report["mem_load_sent_without_mem_fire_cycles"], 1)
        self.assertNotIn("mem_load_sent_without_cache_response_cycles", report)
        self.assertEqual(report["clock_hz"], 132000000)
        self.assertAlmostEqual(report["window_us"], 1024 / 132)
        self.assertAlmostEqual(report["first_to_last_us"], 1023 / 132)
        image = render_svg(samples, "synthetic test fixture", profile=self.profile)
        self.assertIn("132 MHz", image)
        self.assertIn("mem_fire", image)
        self.assertNotIn("d_response", image)
        self.assertFalse(validate_manifest(self.manifest_path, self.profile)["hardware_origin_verified_by_analyzer"])

    def test_old_profiles_cannot_be_substituted(self):
        for profile in ("Legacy27", "Target120"):
            with self.subTest(profile=profile):
                self.write_capture(self.profile)
                with self.assertRaises(ValueError):
                    read_capture(self.capture, profile)
                self.write_capture(profile)
                with self.assertRaises(ValueError):
                    read_capture(self.capture, self.profile)
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, profile)

    def test_mem_invariants(self):
        self.rows[1][1 + 99] = "0"
        self.write_capture()
        with self.assertRaisesRegex(ValueError, "MEM fire/valid"):
            read_capture(self.capture, self.profile)
        self.rows[1][1 + 99] = "1"
        self.rows[1][1 + 107] = "0"
        self.write_capture()
        with self.assertRaisesRegex(ValueError, "MEM-to-WB"):
            read_capture(self.capture, self.profile)

    def test_manifest_semantics_and_clock_rejected(self):
        for key, value in (("Channel107Meaning", "d_response_valid"), ("Channel106Meaning", "i_response_valid"),
                           ("ClockHz", 120000000), ("CaptureDepth", 512), ("TimingConstraintsMet", 1)):
            with self.subTest(key=key):
                old = self.manifest[key]
                self.manifest[key] = value
                self.save_manifest()
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, self.profile)
                self.manifest[key] = old
        self.save_manifest()

    def test_each_artifact_bound(self):
        for relative in self.artifacts.values():
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, self.profile)
                path.write_bytes(original)

    def test_rehashed_wrong_fic(self):
        path = self.root / "cpu.fic"
        original = path.read_text(encoding="utf-8-sig")
        for old, new in (("=board/soc/core/mem_fire", "=board/soc/memory_system/cache_rsp_valid[1]"),
                         ("clockEdge=Rising", "clockEdge=Falling"),
                         ("enableStorageQualification=false", "enableStorageQualification=true"),
                         ("dataDepth=1024", "dataDepth=512")):
            with self.subTest(change=old):
                self.assertEqual(original.count(old), 1)
                path.write_text(original.replace(old, new), encoding="utf-8")
                self.rehash("FicSha256")
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, self.profile)

    def test_rehashed_source_revision_and_configuration(self):
        path = self.root / "source-manifest.json"
        original = path.read_bytes()
        for relative in self.source["SourceSnapshot"]["Files"]:
            source = json.loads(original)
            source["SourceSnapshot"]["Files"][relative] = "0" * 64
            path.write_text(json.dumps(source), encoding="utf-8")
            self.rehash("SourceManifestSha256")
            with self.assertRaisesRegex(ValueError, "source revision"):
                validate_manifest(self.manifest_path, self.profile)
        for field in ("FastDCacheRead", "BtbIndexBits", "EnableM", "TimingConstraintsMet"):
            source = json.loads(original)
            source[field] = 0
            path.write_text(json.dumps(source), encoding="utf-8")
            self.rehash("SourceManifestSha256")
            with self.assertRaisesRegex(ValueError, "source configuration"):
                validate_manifest(self.manifest_path, self.profile)

    def test_original_timing_rejected(self):
        original = self.timing.read_text(encoding="utf-8")
        for old, new in (("All Constraints Met.", "Some Constraints Violated."), ("7.575", "8.333"),
                         ("0.103", "-0.103"), ("Generated (clk) 100", "Generated (clk) 0")):
            with self.subTest(change=old):
                self.timing.write_text(original.replace(old, new), encoding="utf-8")
                with self.assertRaises(ValueError):
                    validate_manifest(self.manifest_path, self.profile)

    def test_cli_requires_manifest(self):
        result = subprocess.run([sys.executable, str(PROJECT / "scripts/ila_analyze.py"),
                                 str(self.capture), "--profile", self.profile, "--symbols", "unused",
                                 "--output", str(self.root / "output")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("matching ILA --manifest", result.stderr)


if __name__ == "__main__":
    unittest.main()
