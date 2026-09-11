import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_fetch_profile as audit

DIRECTORY = audit.ROOT / "build/retirement-profile/20260911-110916-6c2c9a5e"


class RetirementProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = audit.load(DIRECTORY / "invocation.json")
        cls.build = DIRECTORY / cls.receipt["build"]
        cls.baseline = audit.ROOT / "build/compiled" / cls.receipt["baseline"]
        cls.boundaries = cls.receipt["boundaries"]
        cls.image = audit.firmware_image(cls.baseline / "firmware.hex")

    def test_changed_cpu_configuration_or_observer_sources_rejected(self):
        original = audit.runner.load
        for field, value in (("HardwareParameters", {}), ("SourceSnapshot", {}), ("FirmwareSha256", "wrong")):
            with self.subTest(field=field):
                def altered(path):
                    record = copy.deepcopy(original(path))
                    if path == self.build / "manifest.json":
                        record[field] = value
                    return record
                with patch.object(audit.runner, "load", side_effect=altered), self.assertRaises(ValueError):
                    audit.runner.validate_profile(self.build, self.baseline, self.boundaries, self.image)

    def test_changed_uart_rejected(self):
        original = Path.read_bytes
        def altered(path):
            value = original(path)
            return value + b"observer changed output" if path == self.build / "coremark.sim.uart" else value
        with patch.object(Path, "read_bytes", altered), self.assertRaisesRegex(ValueError, "Observer changed raw UART"):
            audit.runner.validate_profile(self.build, self.baseline, self.boundaries, self.image)

    def test_wrong_trace_boundary_and_cycle_span_rejected(self):
        original = audit.runner.load
        for field, value in (("start_pc", 0), ("cycles", 1)):
            with self.subTest(field=field):
                def altered(path):
                    record = copy.deepcopy(original(path))
                    if path == self.build / "coremark.sim.uart.retire.json":
                        record[field] = value
                    return record
                with patch.object(audit.runner, "load", side_effect=altered), self.assertRaises(ValueError):
                    audit.runner.validate_profile(self.build, self.baseline, self.boundaries, self.image)

    def test_profile_compilation_flags_cannot_change_silently(self):
        original = audit.load
        def altered(path):
            record = copy.deepcopy(original(path))
            if path == self.build / "manifest.json":
                record["CompileCommand"] = []
            return record
        with patch.object(audit, "load", side_effect=altered), self.assertRaisesRegex(ValueError, "Profile compiler command changed"):
            audit.audit(DIRECTORY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
