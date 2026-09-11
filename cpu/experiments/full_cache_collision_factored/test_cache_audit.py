import copy
import unittest

from audit_cache_checks import OUTPUT, read_json, validate_coverage


class CacheCoverageTests(unittest.TestCase):
    def sample(self):
        return read_json(OUTPUT / "manifest.json")

    def test_actual_complete_coverage(self):
        self.assertEqual(len(validate_coverage(self.sample())["mutation"]), 10)

    def test_duplicate_writable_configuration_rejected(self):
        record = self.sample()
        cases = [case for case in record["cases"] if case["label"] == "writable"]
        cases[-1]["parameters"] = copy.deepcopy(cases[0]["parameters"])
        with self.assertRaisesRegex(ValueError, "writable configuration"):
            validate_coverage(record)

    def test_missing_parent_bounds_source_rejected(self):
        record = self.sample()
        cases = [case for case in record["cases"] if case["label"] == "bounds"]
        cases[0]["source_sha256"] = cases[1]["source_sha256"]
        with self.assertRaisesRegex(ValueError, "bounds source/configuration"):
            validate_coverage(record)

    def test_compile_failure_is_not_runtime_rejection(self):
        record = self.sample()
        next(case for case in record["cases"] if case["label"] == "mutation")["compile_passed"] = False
        with self.assertRaisesRegex(ValueError, "Uncompiled"):
            validate_coverage(record)

    def test_mutation_success_is_rejected(self):
        record = self.sample()
        next(case for case in record["cases"] if case["label"] == "mutation")["exit_code"] = 0
        with self.assertRaisesRegex(ValueError, "runtime result"):
            validate_coverage(record)


if __name__ == "__main__":
    unittest.main(verbosity=2)
