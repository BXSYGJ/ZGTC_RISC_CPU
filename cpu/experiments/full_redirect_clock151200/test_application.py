import copy
import json
import unittest

from audit_application import ROOT, RUNTIME, validate_pair


class ApplicationPairTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((ROOT / "build/local-application-qualification.json").read_text(encoding="utf-8"))
        self.snapshot = json.loads((RUNTIME / "manifest.json").read_text(encoding="utf-8"))

    def check(self):
        validate_pair(self.result["runtime"], self.result["binding"], self.result["physical"], self.snapshot)

    def test_actual_runtime_physical_pair(self):
        self.check()
        self.assertFalse(self.result["hardware_validated"])
        self.assertFalse(self.result["electrical_qualified"])

    def test_wrong_clock_rejected(self):
        self.result["physical"]["clock_hz"] = 154285714
        with self.assertRaisesRegex(ValueError, "clock mismatch"):
            self.check()

    def test_wrong_firmware_rejected(self):
        self.result["physical"]["inputs_sha256"]["firmware.hex"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "firmware bytes"):
            self.check()

    def test_wrong_rtl_rejected(self):
        self.snapshot["source_snapshot"]["Files"]["rtl/rv32_core.sv"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "RTL source"):
            self.check()

    def test_wrong_parameters_rejected(self):
        self.snapshot["physical_parameters"]["ENABLE_M"] = 0
        with self.assertRaisesRegex(ValueError, "hardware parameters"):
            self.check()

    def test_each_ila_dimension_rejected(self):
        original = copy.deepcopy(self.result["physical"]["ila"])
        for key in ("data_channels", "trigger_channels", "depth"):
            self.result["physical"]["ila"] = dict(original, **{key: original[key] - 1})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "ILA function"):
                self.check()

    def test_failed_or_hardware_labels_rejected(self):
        original = copy.deepcopy(self.result)
        for section, key, value in (("runtime", "simulation_passed", False), ("physical", "physical_timing_passed", False), ("runtime", "hardware_validated", True), ("physical", "hardware_validated", True)):
            self.result = copy.deepcopy(original)
            self.result[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                self.check()


if __name__ == "__main__":
    unittest.main(verbosity=2)
