import copy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from compare_coremark import compare, read_case
from pds_report import parse_reports
from test_coremark_checker import fixture
from test_pds_report import TIMING, LOG


def cases():
    baseline = {"manifest": {"Device": "PG2L200H-6FBB676", "ClockHz": 162000000,
                            "ReferenceClockHz": 27000000, "ClockSource": "GTP_GPLL", "UartProfile": "RemoteLab",
                            "UartBaud": 115200, "Predictor": 1, "LoadUseBubble": 0, "CacheSetBits": 4,
                            "CacheEnabled": 1, "FastICacheHit": 0},
                "sha256": {"FirmwareSha256": "a" * 64}, "report": {"setup_wns_ns": 0.1},
                "result": {"validation_run": False, "reportable_duration": True, "crc_valid": True,
                           "iterations": 1000, "retired": 100000000, "seed_crc": "e9f5", "final_crc": "d340",
                           "clock_hz": 162000000, "cycles": 2700000000, "lut_count": 5000,
                           "iterations_per_second": 60, "iterations_per_second_per_mhz": 60 / 162,
                           "iterations_per_second_per_lut": 60 / 5000}}
    candidate = copy.deepcopy(baseline)
    candidate["manifest"]["FastICacheHit"] = 1
    candidate["result"].update(cycles=2025000000, lut_count=5500, iterations_per_second=80,
                               iterations_per_second_per_mhz=80 / 162, iterations_per_second_per_lut=80 / 5500)
    return baseline, candidate


class ComparisonTests(unittest.TestCase):
    def test_independent_cache_capacity_comparisons(self):
        baseline, candidate = cases()
        candidate["manifest"]["FastICacheHit"] = 0
        candidate["manifest"]["ICacheSetBits"] = 8
        self.assertEqual(compare(baseline, candidate, "ICacheSetBits")["variable"], "ICacheSetBits")
        with self.assertRaisesRegex(ValueError, "Instruction cache geometry differs"):
            compare(baseline, candidate, "CacheSetBits")
        baseline["manifest"]["ICacheSetBits"] = 8
        candidate["manifest"]["CacheSetBits"] = 6
        self.assertEqual(compare(baseline, candidate, "CacheSetBits")["variable"], "CacheSetBits")
        with self.assertRaisesRegex(ValueError, "CacheSetBits"):
            compare(baseline, candidate, "ICacheSetBits")
        candidate["manifest"]["CacheSetBits"] = 4
        with self.assertRaisesRegex(ValueError, "distinct valid widths"):
            compare(baseline, candidate, "ICacheSetBits")
        for invalid in (0, 9, True, "8"):
            candidate["manifest"]["ICacheSetBits"] = invalid
            with self.assertRaisesRegex(ValueError, "cache geometry"):
                compare(baseline, candidate, "ICacheSetBits")

    def test_three_metrics_and_resource_cost(self):
        baseline, candidate = cases()
        result = compare(baseline, candidate)
        self.assertAlmostEqual(result["metrics"]["execution_efficiency"]["change_percent"], 100 / 3)
        self.assertAlmostEqual(result["metrics"]["resource_efficiency"]["change_percent"], 21.2121212121)
        self.assertAlmostEqual(result["metrics"]["post_route_luts"]["change_percent"], 10)
        self.assertAlmostEqual(result["metrics"]["cycles"]["change_percent"], -25)
        self.assertFalse(result["board_identity_verified_by_this_tool"])

    def test_overlap_changes_are_not_early_hit_ablation(self):
        baseline, candidate = cases()
        candidate["manifest"]["FetchOverlap"] = 1
        with self.assertRaisesRegex(ValueError, "overlapping fetch differs"):
            compare(baseline, candidate)
        baseline["manifest"]["FetchOverlap"] = 1
        compare(baseline, candidate)

    def test_explicit_overlap_ablation(self):
        baseline, candidate = cases()
        baseline["manifest"]["FastICacheHit"] = 1
        candidate["manifest"]["FetchOverlap"] = 1
        self.assertEqual(compare(baseline, candidate, "FetchOverlap")["variable"], "FetchOverlap")
        candidate["manifest"]["FastICacheHit"] = 0
        with self.assertRaisesRegex(ValueError, "Early-hit setting differs"):
            compare(baseline, candidate, "FetchOverlap")
        candidate["manifest"]["FastICacheHit"] = 1
        candidate["manifest"]["FetchOverlap"] = 0
        with self.assertRaises(ValueError):
            compare(baseline, candidate, "FetchOverlap")
        with self.assertRaisesRegex(ValueError, "Unsupported comparison"):
            compare(baseline, candidate, "EnableM")

    def test_explicit_dcache_write_ablation(self):
        baseline, candidate = cases()
        baseline["manifest"]["FastICacheHit"] = 1
        candidate["manifest"]["FastDCacheWrite"] = 1
        self.assertEqual(compare(baseline, candidate, "FastDCacheWrite")["variable"], "FastDCacheWrite")
        with self.assertRaisesRegex(ValueError, "Early D-cache write setting differs"):
            compare(baseline, candidate)
        for invalid in (True, 0, 2, "1", None):
            candidate["manifest"]["FastDCacheWrite"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compare(baseline, candidate, "FastDCacheWrite")
        candidate["manifest"]["FastDCacheWrite"] = 1
        candidate["manifest"]["FastDCacheRead"] = 1
        with self.assertRaisesRegex(ValueError, "Early D-cache read setting differs"):
            compare(baseline, candidate, "FastDCacheWrite")

    def test_explicit_dcache_read_ablation(self):
        baseline, candidate = cases()
        baseline["manifest"]["FastICacheHit"] = 1
        candidate["manifest"]["FastDCacheRead"] = 1
        self.assertEqual(compare(baseline, candidate, "FastDCacheRead")["variable"], "FastDCacheRead")
        with self.assertRaisesRegex(ValueError, "Early D-cache read setting differs"):
            compare(baseline, candidate)
        candidate["manifest"]["FetchOverlap"] = 1
        with self.assertRaisesRegex(ValueError, "overlapping fetch differs"):
            compare(baseline, candidate, "FastDCacheRead")

    def test_explicit_early_request_ablation(self):
        baseline, candidate = cases()
        baseline["manifest"]["FastICacheHit"] = 1
        candidate["manifest"]["EarlyDRequest"] = 1
        self.assertEqual(compare(baseline, candidate, "EarlyDRequest")["variable"], "EarlyDRequest")
        with self.assertRaises(ValueError):
            compare(baseline, candidate)
        candidate["manifest"]["FetchOverlap"] = 1
        with self.assertRaisesRegex(ValueError, "overlapping fetch differs"):
            compare(baseline, candidate, "EarlyDRequest")

    def test_explicit_btb_capacity_ablation(self):
        baseline, candidate = cases()
        candidate["manifest"]["FastICacheHit"] = 0
        candidate["manifest"]["BtbIndexBits"] = 6
        self.assertEqual(compare(baseline, candidate, "BtbIndexBits")["variable"], "BtbIndexBits")
        with self.assertRaisesRegex(ValueError, "BTB capacity differs"):
            compare(baseline, candidate)
        for invalid in (True, 0, 4, 9, "6", None):
            candidate["manifest"]["BtbIndexBits"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                compare(baseline, candidate, "BtbIndexBits")
        candidate["manifest"]["BtbIndexBits"] = 6
        baseline["manifest"]["Predictor"] = candidate["manifest"]["Predictor"] = 0
        with self.assertRaisesRegex(ValueError, "enabled prediction"):
            compare(baseline, candidate, "BtbIndexBits")

    def test_explicit_data_overlap_ablation(self):
        baseline, candidate = cases()
        candidate["manifest"]["FastICacheHit"] = 0
        candidate["manifest"]["DataOverlap"] = 1
        self.assertEqual(compare(baseline, candidate, "DataOverlap")["variable"], "DataOverlap")
        with self.assertRaisesRegex(ValueError, "Data request overlap differs"):
            compare(baseline, candidate)
        candidate["manifest"]["BtbIndexBits"] = 6
        with self.assertRaisesRegex(ValueError, "BTB capacity differs"):
            compare(baseline, candidate, "DataOverlap")

    def test_matching_source_snapshot_requirement(self):
        baseline, candidate = cases()
        self.assertFalse(compare(baseline, candidate)["same_source_snapshot_verified"])
        for case in (baseline, candidate):
            case["source_snapshot_verified"] = True
            case["manifest"]["SourceSnapshot"] = {"Schema": 1, "Files": {"rtl/core.sv": "a" * 64}}
        self.assertTrue(compare(baseline, candidate)["same_source_snapshot_verified"])
        candidate["manifest"]["SourceSnapshot"]["Files"]["rtl/core.sv"] = "A" * 64
        self.assertTrue(compare(baseline, candidate)["same_source_snapshot_verified"])
        candidate["manifest"]["SourceSnapshot"]["Files"]["rtl/core.sv"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "source snapshots differ"):
            compare(baseline, candidate)

    def test_changed_controls_rejected(self):
        for key in ("Device", "ClockHz", "ReferenceClockHz", "ClockSource", "UartProfile", "UartBaud",
                    "Predictor", "LoadUseBubble", "CacheSetBits", "CacheEnabled"):
            baseline, candidate = cases()
            candidate["manifest"][key] = "different"
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare(baseline, candidate)

    def test_wrong_firmware_and_flag(self):
        baseline, candidate = cases()
        candidate["sha256"]["FirmwareSha256"] = "b" * 64
        with self.assertRaises(ValueError):
            compare(baseline, candidate)
        baseline, candidate = cases()
        candidate["manifest"]["FastICacheHit"] = 0
        with self.assertRaises(ValueError):
            compare(baseline, candidate)

    def test_invalid_workload_rejected(self):
        for key, value in (("validation_run", True), ("reportable_duration", False), ("crc_valid", False),
                           ("iterations", 4000), ("retired", 1), ("seed_crc", "18f2"), ("final_crc", "65c5"),
                           ("clock_hz", 180000000), ("lut_count", 0)):
            baseline, candidate = cases()
            candidate["result"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare(baseline, candidate)

    def test_resource_efficiency_can_degrade(self):
        baseline, candidate = cases()
        candidate["result"].update(lut_count=10000, iterations_per_second_per_lut=80 / 10000)
        result = compare(baseline, candidate)
        self.assertGreater(result["metrics"]["execution_efficiency"]["change_percent"], 0)
        self.assertLess(result["metrics"]["resource_efficiency"]["change_percent"], 0)

    def test_m_extension_is_a_control_not_an_icache_change(self):
        baseline, candidate = cases()
        candidate["manifest"]["EnableM"] = 1
        with self.assertRaises(ValueError):
            compare(baseline, candidate)


class ArtifactComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "report_timing").mkdir()
        (self.root / "generate_bitstream").mkdir()
        (self.root / "report_timing/pds_soc_top.rtr").write_text(TIMING, encoding="utf-8")
        (self.root / "run.log").write_text(LOG, encoding="utf-8")
        (self.root / "firmware.hex").write_bytes(b"synthetic firmware")
        (self.root / "generate_bitstream/pds_soc_top.sbit").write_bytes(b"synthetic bitstream")
        self.manifest = {"Device": "PG2L200H-6FBB676", "ClockHz": 108000000,
                         "TimingConstraintsMet": True, "ResourceSummary": parse_reports(TIMING, LOG, 108000000),
                         "FirmwareSha256": sha256(b"synthetic firmware").hexdigest(),
                         "BitstreamSha256": sha256(b"synthetic bitstream").hexdigest(),
                         "Predictor": 1, "LoadUseBubble": 0, "CacheEnabled": 1, "FastICacheHit": 0,
                         "CacheSetBits": 4}
        self.save_manifest()
        self.uart = self.root / "capture.uart"
        self.text = fixture(cycles=1296000000, clock_hz=108000000) + "\nZGTC config=0e020401 ihit=1 imiss=2 dhit=3 dmiss=4 writebacks=5\n"
        self.uart.write_text(self.text, encoding="utf-8")

    def save_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8-sig")

    def test_instruction_geometry_manifest_and_uart_agree(self):
        self.manifest["ICacheSetBits"] = 8
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e028401"), encoding="utf-8")
        result = read_case(self.root, self.uart)["result"]["profile"]
        self.assertEqual((result["icache_set_bits"], result["dcache_set_bits"]), (8, 4))
        for key in ("ICacheSetBits", "CacheSetBits"):
            original = self.manifest[key]
            for invalid in (0, 9, True, "8", None):
                self.manifest[key] = invalid
                self.save_manifest()
                with self.subTest(key=key, invalid=invalid), self.assertRaisesRegex(ValueError, "cache geometry"):
                    read_case(self.root, self.uart)
            self.manifest[key] = original
        self.manifest["ICacheSetBits"] = 4
        self.save_manifest()
        self.uart.write_text(self.text, encoding="utf-8")
        self.assertEqual(read_case(self.root, self.uart)["result"]["profile"]["icache_set_bits"], 4)

    def test_read_case_uses_raw_reports_and_hashes(self):
        case = read_case(self.root, self.uart)
        self.assertEqual(case["result"]["lut_count"], 4551)
        self.assertEqual(case["sha256"]["uart"], sha256(self.uart.read_bytes()).hexdigest())

    def test_overlap_manifest_and_uart_agree(self):
        self.manifest["FetchOverlap"] = 1
        self.save_manifest()
        with self.assertRaises(ValueError):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e020421"), encoding="utf-8")
        self.assertTrue(read_case(self.root, self.uart)["result"]["profile"]["fetch_overlap"])
        for invalid in (True, -1, 2, "1", None):
            self.manifest["FetchOverlap"] = invalid
            self.save_manifest()
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Invalid overlapping fetch"):
                read_case(self.root, self.uart)

    def test_dcache_manifest_and_uart_agree(self):
        self.manifest["FastDCacheRead"] = 1
        self.save_manifest()
        with self.assertRaises(ValueError):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e020441"), encoding="utf-8")
        self.assertTrue(read_case(self.root, self.uart)["result"]["profile"]["fast_dcache_read"])
        for invalid in (True, -1, 2, "1", None):
            self.manifest["FastDCacheRead"] = invalid
            self.save_manifest()
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Invalid early D-cache read"):
                read_case(self.root, self.uart)

    def test_early_request_manifest_and_uart_agree(self):
        self.manifest["EarlyDRequest"] = 1
        self.save_manifest()
        with self.assertRaises(ValueError):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e020481"), encoding="utf-8")
        self.assertTrue(read_case(self.root, self.uart)["result"]["profile"]["early_d_request"])
        for invalid in (True, -1, 2, "1", None):
            self.manifest["EarlyDRequest"] = invalid
            self.save_manifest()
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                read_case(self.root, self.uart)

    def test_btb_manifest_and_uart_agree(self):
        self.assertEqual(read_case(self.root, self.uart)["result"]["profile"]["btb_index_bits"], 4)
        self.manifest["BtbIndexBits"] = 6
        self.save_manifest()
        with self.assertRaises(ValueError):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e620401"), encoding="utf-8")
        self.assertEqual(read_case(self.root, self.uart)["result"]["profile"]["btb_index_bits"], 6)
        for invalid in (True, 0, 9, "6", None):
            self.manifest["BtbIndexBits"] = invalid
            self.save_manifest()
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Invalid BTB"):
                read_case(self.root, self.uart)

    def test_data_overlap_manifest_and_uart_agree(self):
        self.manifest["DataOverlap"] = 1
        self.save_manifest()
        with self.assertRaises(ValueError):
            read_case(self.root, self.uart)
        self.uart.write_text(self.text.replace("0e020401", "0e060401"), encoding="utf-8")
        self.assertTrue(read_case(self.root, self.uart)["result"]["profile"]["data_overlap"])
        for invalid in (True, -1, 2, "1", None):
            self.manifest["DataOverlap"] = invalid
            self.save_manifest()
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Invalid data request overlap"):
                read_case(self.root, self.uart)

    def test_source_snapshot_integrity(self):
        self.assertFalse(read_case(self.root, self.uart)["source_snapshot_verified"])
        source = self.root / "source/rtl/core.sv"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"module core; endmodule")
        self.manifest["SourceSnapshot"] = {"Schema": 1, "Files": {"rtl/core.sv": sha256(source.read_bytes()).hexdigest()}}
        self.save_manifest()
        self.assertTrue(read_case(self.root, self.uart)["source_snapshot_verified"])
        source.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source snapshot hash mismatch"):
            read_case(self.root, self.uart)
        source.unlink()
        with self.assertRaisesRegex(ValueError, "source snapshot inventory differs"):
            read_case(self.root, self.uart)
        self.manifest["SourceSnapshot"]["Schema"] = True
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "source snapshot schema"):
            read_case(self.root, self.uart)

    def test_artifact_tamper_rejected(self):
        for relative in ("firmware.hex", "generate_bitstream/pds_soc_top.sbit"):
            path = self.root / relative
            original = path.read_bytes()
            path.write_bytes(original + b"changed")
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "Artifact hash mismatch"):
                read_case(self.root, self.uart)
            path.write_bytes(original)

    def test_manifest_resource_tamper_rejected(self):
        self.manifest["ResourceSummary"]["resources"]["post_route_luts"] -= 1
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Manifest resources differ"):
            read_case(self.root, self.uart)

    def test_mixed_and_mismatched_uart_rejected(self):
        for text in (self.text + self.text, self.text.replace("0e020401", "0e020409"),
                     self.text.replace("clock_hz=108000000", "clock_hz=120000000")):
            self.uart.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                read_case(self.root, self.uart)


if __name__ == "__main__":
    unittest.main()
