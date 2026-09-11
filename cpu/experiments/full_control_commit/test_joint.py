import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from audit_joint import CPU, digest, read_run


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

    def test_rehashed_fabricated_cycle_count_rejected(self):
        filename = self.directory / "result.json"
        result = json.loads(filename.read_text(encoding="utf-8"))
        result["cycles"] -= 1
        filename.write_text(json.dumps(result), encoding="utf-8")
        self.manifest["ResultSha256"] = digest(filename)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Stored long result differs"):
            self.evaluate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
