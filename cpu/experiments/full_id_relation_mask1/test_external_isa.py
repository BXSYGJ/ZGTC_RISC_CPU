import copy
import unittest
from audit_external_isa import CONFIGURATIONS, REJECTIONS, validate_coverage


class CoverageTests(unittest.TestCase):
    def sample(self):
        return {"status": "passed", "suite": "rv32ui", "tests": ["add", "jalr"],
                "results": [{"name": name, "configuration": config} for name in ("add", "jalr") for config in sorted(CONFIGURATIONS)],
                "negative_controls": [{"name": name, "expected_rejection": text} for name, text in REJECTIONS.items()]}

    def test_complete_cartesian_coverage(self):
        validate_coverage(self.sample(), ["add", "jalr"], "rv32ui")

    def test_duplicate_pair_cannot_replace_missing_pair(self):
        sample = self.sample()
        sample["results"][-1] = copy.deepcopy(sample["results"][0])
        with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
            validate_coverage(sample, ["add", "jalr"], "rv32ui")

    def test_incomplete_state_and_wrong_upstream_set(self):
        for field, value in (("status", "running"), ("tests", ["add"])):
            sample = self.sample()
            sample[field] = value
            with self.assertRaises(ValueError):
                validate_coverage(sample, ["add", "jalr"], "rv32ui")

    def test_wrong_rejection_control_is_not_success(self):
        sample = self.sample()
        sample["negative_controls"][-1]["expected_rejection"] = "PASS ISA"
        with self.assertRaisesRegex(ValueError, "rejection controls"):
            validate_coverage(sample, ["add", "jalr"], "rv32ui")


if __name__ == "__main__":
    unittest.main(verbosity=2)
