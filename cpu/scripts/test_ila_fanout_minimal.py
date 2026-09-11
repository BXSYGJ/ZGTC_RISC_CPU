import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ila_analyze import header_for, read_capture, summarize, validate_manifest


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "RegfileFanout157500Minimal"


class MinimalFanoutIlaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest_path = self.root / "manifest.json"
        snapshot = {"Schema":1,"Files":json.loads((ROOT / "scripts/ila_regfilefanout157500_sources.json").read_text())}
        self.source = {"Schema":1,"Profile":PROFILE,"Device":"PG2L200H-6FBB676","ClockHz":157500000,
                       "UartProfile":"RemoteLab","UartBaud":115200,"SourceTimingConstraintsMet":False,
                       "SourceAcceptedManifest":False,"FullScoreQualified":False,"HardwareValidated":False,
                       "Scope":"audited_synthesis_input_for_independent_ILA_implementation_not_timing_or_score_qualification",
                       "SourceSnapshot":snapshot}
        self.manifest = {"Profile":PROFILE,"Device":"PG2L200H-6FBB676","ClockHz":157500000,
                         "SampleClockNet":"cpu_clk","CaptureChannels":42,"CaptureDepth":1024,
                         "TimingConstraintsMet":True,"Channel39Meaning":"mem_flush","Channel40Meaning":"fetch_complete","Channel41Meaning":"mem_fire",
                         "TriggerChannels":33,"TriggerMatchType":0,"DataEqualsTrigger":False,
                         "SourceTimingConstraintsMet":False,"SourceAcceptedManifest":False,"SourceSnapshot":snapshot}
        self.artifacts = {"SourceAdfSha256":"source.adf","SourceNetlistSha256":"netlist.v","FirmwareSha256":"firmware.hex",
                          "BitstreamSha256":"generate_bitstream/pds_soc_top.sbit","FicSha256":"cpu.fic",
                          "SourceCandidateSha256":"source-candidate.json"}
        for key, relative in self.artifacts.items():
            if key == "SourceCandidateSha256":
                continue
            artifact = self.root / relative
            artifact.parent.mkdir(parents=True,exist_ok=True)
            data = ((ROOT / "scripts/cpu_ila_regfilefanout157500_minimal.fic.in").read_bytes() if key == "FicSha256" else ("synthetic fixture "+relative).encode())
            artifact.write_bytes(data)
            self.manifest[key] = hashlib.sha256(data).hexdigest()
            if key in ("SourceAdfSha256","SourceNetlistSha256","FirmwareSha256"):
                self.source[key] = self.manifest[key]
        (self.root / "verify.stdout.txt").write_bytes((ROOT / "build/ila-probe/regfilefanout157500-minimal-named/stdout.txt").read_bytes())
        self.save_source()
        self.timing = self.root / "report_timing/pds_soc_top.rtr"
        self.timing.parent.mkdir()
        self.timing.write_text("| Device : PG2L200H\n| Speed Grade : -6\n| Package : FBB676\n"
                               "Design Summary : All Constraints Met.\n"
                               "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 6.3490 {0 3.1740} Generated (clk) 100\n"
                               "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 157.5051 MHz 158.757 MHz 6.3490 6.2990 0.050\n")
        (self.root / "run.log").write_text("Device Utilization Summary :\n"
                                           "| Use of CLMA | 100 |\n| FF | 4500 |\n| LUT | 7600 |\n"
                                           "| Use of CLMS | 100 |\n| FF | 800 |\n| LUT | 2342 |\n"
                                           "| Use of DRM | 24.5 |\n| Use of GPLL | 1 |\n| Use of APM | 4 |\n")
        validate_manifest(self.manifest_path,PROFILE)

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest),encoding="utf-8-sig")

    def save_source(self):
        path = self.root / "source-candidate.json"
        path.write_text(json.dumps(self.source),encoding="utf-8")
        self.manifest["SourceCandidateSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save_manifest()

    def test_matching_candidate_timing_and_total_resources(self):
        result = validate_manifest(self.manifest_path,PROFILE)
        self.assertEqual(result["physical_summary"]["resources"]["post_route_luts"],9942)
        self.assertFalse(result["hardware_origin_verified_by_analyzer"])
        self.assertFalse(result["score_qualification_verified_by_analyzer"])
        self.assertIn("source-candidate.json",result["artifacts_sha256"])

    def test_failed_source_must_not_be_relabelled(self):
        for key in ("SourceTimingConstraintsMet","SourceAcceptedManifest"):
            self.manifest[key] = True
            self.save_manifest()
            with self.assertRaisesRegex(ValueError,"source qualification"):
                validate_manifest(self.manifest_path,PROFILE)
            self.manifest[key] = False
        self.save_manifest()
        for key in ("SourceTimingConstraintsMet","SourceAcceptedManifest","FullScoreQualified","HardwareValidated"):
            self.source[key] = True
            self.save_source()
            with self.assertRaisesRegex(ValueError,"source configuration"):
                validate_manifest(self.manifest_path,PROFILE)
            self.source[key] = False
            self.save_source()

    def test_rehashed_source_or_trigger_changes_rejected(self):
        self.source["SourceAdfSha256"] = "0"*64
        self.save_source()
        with self.assertRaisesRegex(ValueError,"candidate artifact"):
            validate_manifest(self.manifest_path,PROFILE)
        self.source["SourceAdfSha256"] = self.manifest["SourceAdfSha256"]
        self.save_source()
        fic = self.root / "cpu.fic"
        fic.write_text(fic.read_text().replace("triggerMatchType<0>=0","triggerMatchType<0>=1"))
        self.manifest["FicSha256"] = hashlib.sha256(fic.read_bytes()).hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError,"property"):
            validate_manifest(self.manifest_path,PROFILE)

    def test_raw_timing_failure_and_wrong_device_rejected(self):
        original = self.timing.read_text()
        for before,after in (("All Constraints Met.","Some Constraints Violated."),("0.050","-0.050"),("PG2L200H","PG2L100H"),("6.3490","7.5750")):
            self.timing.write_text(original.replace(before,after))
            with self.assertRaises(ValueError):
                validate_manifest(self.manifest_path,PROFILE)
        self.timing.write_text(original)
        for profile in ("Target132Kept","Target132Carry","Target120"):
            with self.assertRaises(ValueError):
                validate_manifest(self.manifest_path,profile)

    def test_exact_capture_frequency_and_mem_fire_semantics(self):
        capture = self.root / "capture.csv"
        with capture.open("w",newline="",encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(header_for(PROFILE))
            writer.writerows([[str(index)]+["0"]*42 for index in range(1024)])
        samples = read_capture(capture,PROFILE)
        result = summarize(samples,[],PROFILE)
        self.assertEqual(result["clock_hz"],157500000)
        self.assertAlmostEqual(result["window_us"],1024/157.5)
        self.assertIn("mem_held_cycles",result)
        self.assertNotIn("mem_load_sent_without_mem_fire_cycles",result)
        self.assertNotIn("id_pc",samples[0])
        self.assertIsNone(result["window_cycles_per_wb_event"])
        self.assertNotIn("d_response",samples[0])



    def write_samples(self, rows):
        capture = self.root / "pipeline.csv"
        with capture.open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(header_for(PROFILE))
            writer.writerows([[str(index)] + list(map(str, row)) for index, row in enumerate(rows)])
        return capture

    def test_nonzero_pipeline_pc_and_local_throughput(self):
        address = 0x12345678
        bits = [(address >> bit) & 1 for bit in range(32)] + [1, 1, 1, 1, 1, 1, 1, 0, 1, 1]
        capture = self.write_samples([bits] * 1024)
        samples = read_capture(capture, PROFILE)
        result = summarize(samples, [(address, 4, "synthetic_core_matrix")], PROFILE)
        self.assertEqual(samples[0]["ex_pc"], address)
        self.assertEqual(result["window_wb_per_cycle"], 1)
        self.assertEqual(result["window_cycles_per_wb_event"], 1)
        self.assertEqual(result["ex_fire_function_counts"], {"synthetic_core_matrix": 1024})
        self.assertEqual(result["mem_held_cycles"], 0)
        for key in ("id_pc", "if_pc", "mem_load", "mem_sent", "i_command"):
            self.assertNotIn(key, samples[0])
        from ila_analyze import render_svg
        drawing = render_svg(samples, "synthetic <not hardware>", length=16, profile=PROFILE)
        self.assertIn("157.5 MHz", drawing)
        self.assertIn("fetch_complete", drawing)
        self.assertIn("EX_PC", drawing)
        self.assertIn("12345678", drawing)
        self.assertIn("&lt;not hardware&gt;", drawing)

    def test_compact_width_binary_order_and_temporal_controls(self):
        base = [[0] * 42 for _ in range(1024)]
        controls = ((37, 0), (38, 0), (41, 0), (37, 33), (38, 34), (36, 0))
        for fire_bit, valid_bit in controls:
            rows = [row.copy() for row in base]
            rows[1][fire_bit] = 1
            if valid_bit:
                rows[1][valid_bit] = 1
            with self.subTest(fire=fire_bit, valid=valid_bit):
                with self.assertRaises(ValueError):
                    read_capture(self.write_samples(rows), PROFILE)
        for bit in range(42):
            rows = [row.copy() for row in base]
            rows[7][bit] = "X"
            with self.assertRaises(ValueError):
                read_capture(self.write_samples(rows), PROFILE)
        for width in (41, 43, 109):
            with self.assertRaises(ValueError):
                read_capture(self.write_samples([[0] * width] * 1024), PROFILE)
        capture = self.write_samples(base)
        original = capture.read_text(encoding="utf-8-sig")
        capture.write_text(original.replace("\n5,", "\n6,"), encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            read_capture(capture, PROFILE)
        print("PASS compact decoder six fire/temporal, 42 X-bit, three width and one index controls")

    def test_actual_map_output_cannot_be_forged_by_hash_only(self):
        output = self.root / "verify.stdout.txt"
        original = output.read_text()
        for old, new in (("Data Channel 41:", "Data Channel 42:"), ("Trigger Channel 32:", "Trigger Channel 33:"),
                         ("Clock Port channel:", "Wrong clock:")):
            output.write_text(original.replace(old, new))
            with self.assertRaises(ValueError):
                validate_manifest(self.manifest_path, PROFILE)
        output.write_text(original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
