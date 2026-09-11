import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from audit_joint import CPU, ROOT, RUNS, audit_binding, digest, read_run


class LongBindingTests(unittest.TestCase):
    def setUp(self):
        self.current_root = CPU / "experiments/full_mul_precompute_compare"
        source = self.current_root / "build/compiled/20260910-191854-9844bd02"
        self.manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        physical = self.current_root / "build/pds/20260910-185805-fa3b42e6"
        snapshot = json.loads((physical / "source-snapshot.json").read_text(encoding="utf-8-sig"))
        self.binding = {"hardware_parameters": copy.deepcopy(self.manifest["HardwareParameters"]), "clock_hz": 157500000,
                        "physical_firmware_sha256": digest(physical / "firmware.hex"), "physical_source_hashes": snapshot["Files"]}
        self.temporary = tempfile.TemporaryDirectory(prefix="long-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        filenames = ["manifest.json", "firmware.hex", "coremark.sim.uart", "result.json", "objects/Vrv32_soc"]
        filenames += ["source/" + relative for relative in self.manifest["SourceSnapshot"]]
        for relative in filenames:
            destination = self.directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)

    def evaluate(self):
        return read_run(self.directory, self.binding, False, self.current_root)

    def save_manifest(self):
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_actual_completed_long_fixture(self):
        self.assertEqual(self.evaluate()["cycles"], 1831572143)

    def test_unfinished_run_rejected(self):
        self.manifest["SimulationPassed"] = False
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Long simulation not complete"):
            self.evaluate()

    def test_wrong_physical_parameters_rejected(self):
        self.binding["hardware_parameters"]["ENABLE_M"] = 0
        with self.assertRaisesRegex(ValueError, "hardware parameters differ"):
            self.evaluate()

    def test_wrong_physical_firmware_rejected(self):
        self.binding["physical_firmware_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "firmware differs"):
            self.evaluate()

    def test_wrong_physical_rtl_rejected(self):
        self.binding["physical_source_hashes"]["rtl/rv32_core.sv"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "RTL differs"):
            self.evaluate()

    def test_wrong_physical_clock_rejected(self):
        self.binding["clock_hz"] = 151200000
        with self.assertRaisesRegex(ValueError, "configuration clock differs"):
            self.evaluate()

    def test_omitted_source_rejected(self):
        for relative in ("rtl/rv32_core.sv", "sim/coremark_compiled.cpp", "scripts/check_coremark.py"):
            with self.subTest(relative=relative):
                expected = self.manifest["SourceSnapshot"].pop(relative)
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, "simulation source set"):
                    self.evaluate()
                self.manifest["SourceSnapshot"][relative] = expected

    def test_changed_compiler_parameters_rejected(self):
        original = list(self.manifest["CompileCommand"])
        for before, after in (("-GENABLE_M=1", "-GENABLE_M=0"), ("-GCLOCK_HZ=3200", "-GCLOCK_HZ=6400"), ("-GBAUD=100", "-GBAUD=200")):
            self.assertIn(before, original)
            with self.subTest(argument=before):
                self.manifest["CompileCommand"] = [after if value == before else value for value in original]
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, "Compile command differs"):
                    self.evaluate()

    def test_altered_captured_configuration_rejected(self):
        self.manifest["ConfigurationInput"]["EnableM"] = 0
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "configuration hardware differs"):
            self.evaluate()

    def test_mislabeled_hardware_result_rejected(self):
        self.manifest["MeasurementKind"] = "hardware"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "measurement label"):
            self.evaluate()

    def test_rehashed_fabricated_cycle_count_rejected(self):
        filename = self.directory / "result.json"
        result = json.loads(filename.read_text(encoding="utf-8"))
        result["cycles"] -= 1
        filename.write_text(json.dumps(result), encoding="utf-8")
        self.manifest["ResultSha256"] = digest(filename)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Stored long result differs"):
            self.evaluate()


class CurrentCandidateTests(unittest.TestCase):
    def test_actual_completed_candidate_pair(self):
        for validation, compiled, source, physical in RUNS:
            with self.subTest(validation=validation):
                binding = audit_binding(ROOT / "build/pds" / source, validation)
                result = read_run(ROOT / "build/compiled" / compiled, binding, validation)
                self.assertEqual(result["clock_hz"], 151200000)
                self.assertEqual(result["cycles"], 1799846469 if validation else 1797640625)
                self.assertTrue(result["crc_valid"])
                self.assertTrue(result["modeled_duration_at_least_10s"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
