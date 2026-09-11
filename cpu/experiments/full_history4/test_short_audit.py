import json
import shutil
import tempfile
import unittest
from pathlib import Path

from audit_short import ROOT, digest, read_run


class ShortAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clock-short-audit-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        source = ROOT / "build/compiled/20260910-212254-4ae1d8bd"
        self.manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        filenames = ["manifest.json", "firmware.hex", "coremark.sim.uart", "result.json", "objects/Vrv32_soc"]
        filenames += ["source/" + name for name in self.manifest["SourceSnapshot"]]
        for relative in filenames:
            destination = self.directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, destination)

    def save_manifest(self):
        (self.directory / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_actual_short_run_passes(self):
        manifest, result = read_run(self.directory)
        self.assertEqual(result["cycles"], 3053191)
        self.assertEqual(result["clock_hz"], 154285714)
        self.assertEqual(manifest["FirmwareBuild"]["Iterations"], 10)

    def test_failed_simulation_rejected(self):
        self.manifest["SimulationPassed"] = False
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Simulation not passed"):
            read_run(self.directory)

    def test_executable_and_source_mutations_rejected(self):
        for relative in ("objects/Vrv32_soc", "source/rtl/rv32_peripherals.sv", "source/rtl/rv32_uart.sv"):
            with self.subTest(relative=relative):
                filename = self.directory / relative
                original = filename.read_bytes()
                filename.write_bytes(original + b"mutation")
                try:
                    with self.assertRaisesRegex(ValueError, "changed"):
                        read_run(self.directory)
                finally:
                    filename.write_bytes(original)

    def test_firmware_hash_mismatch_rejected(self):
        self.manifest["FirmwareBuild"]["HexSha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Firmware manifest hash mismatch"):
            read_run(self.directory)

    def test_rehashed_result_fabrication_rejected(self):
        filename = self.directory / "result.json"
        result = json.loads(filename.read_text(encoding="utf-8"))
        result["cycles"] -= 1
        filename.write_text(json.dumps(result), encoding="utf-8")
        self.manifest["ResultSha256"] = digest(filename)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Stored result differs"):
            read_run(self.directory)

    def test_uart_mutation_rejected(self):
        filename = self.directory / "coremark.sim.uart"
        filename.write_bytes(filename.read_bytes() + b"mutation")
        with self.assertRaisesRegex(ValueError, "Output changed"):
            read_run(self.directory)


if __name__ == "__main__":
    unittest.main(verbosity=2)

