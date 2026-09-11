import copy
import unittest
from unittest.mock import patch

import audit_fetch_joint as joint
import audit_fetch_long as long_audit

PERFORMANCE = joint.ROOT / "build/compiled/20260911-102437-50412c5f"
STAGE = joint.ROOT / "build/ila/fetch-commit-seed1-native-wb"


class JointQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = joint.load(PERFORMANCE / "manifest.json")
        cls.run_record = {"result": joint.load(PERFORMANCE / "result.json")}
        cls.physical = joint.load(STAGE / "physical-qualification.json")

    def test_actual_performance_structural_join(self):
        measured = joint.validate_join(self.run_record, self.manifest, self.physical, False)
        self.assertEqual((measured.iterations, measured.cycles, measured.clock_hz, measured.luts), (6000, 1795360650, 153000000, 9502))
        self.assertTrue(joint.compare_score_resource_tradeoff(joint.BASELINE, measured)["allowed"])

    def test_rejects_incomplete_or_mixed_physical_evidence(self):
        mutations = [("physical_timing_passed", False), ("constraints_met", False), ("clock_hz", 151200000),
                     ("ila", dict(self.physical["ila"], data_channels=41))]
        for field, value in mutations:
            with self.subTest(field=field):
                physical = copy.deepcopy(self.physical)
                physical[field] = value
                with self.assertRaises(ValueError):
                    joint.validate_join(self.run_record, self.manifest, physical, False)
        for field in ("firmware_sha256", "hardware_parameters", "physical_source_hashes"):
            with self.subTest(binding=field):
                physical = copy.deepcopy(self.physical)
                physical["source_binding"][field] = {} if field != "firmware_sha256" else "wrong"
                with self.assertRaises(ValueError):
                    joint.validate_join(self.run_record, self.manifest, physical, False)

    def test_rejects_invalid_full_system_denominator(self):
        for luts in (0, -1, True, 9502.0):
            with self.subTest(luts=luts):
                physical = copy.deepcopy(self.physical)
                physical["resources"]["post_route_luts"] = luts
                with self.assertRaises(ValueError):
                    joint.validate_join(self.run_record, self.manifest, physical, False)

    def test_rejects_wrong_seed_short_run_or_failed_crc(self):
        for field, value in (("validation_run", True), ("iterations", 10), ("crc_valid", False), ("modeled_duration_at_least_10s", False)):
            with self.subTest(field=field):
                run = copy.deepcopy(self.run_record)
                run["result"][field] = value
                with self.assertRaises(ValueError):
                    joint.validate_join(run, self.manifest, self.physical, False)

    def test_actual_long_terminal(self):
        terminal = long_audit.validate_terminal(PERFORMANCE, self.manifest)
        self.assertEqual(terminal["total_simulation_cycles"], 4681722617)
        self.assertGreater(terminal["total_simulation_cycles"], self.run_record["result"]["cycles"])

    def test_terminal_rejects_unfinished_mislabeled_or_reversed_interval(self):
        for field, value in (("SimulationPassed", False), ("MeasurementKind", "hardware"), ("SimulationBackend", "unknown"), ("CompletedUtc", "2026-09-10T00:00:00+00:00")):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest[field] = value
                with self.assertRaises(ValueError):
                    long_audit.validate_terminal(PERFORMANCE, manifest)

    def test_joint_still_requires_actual_pair(self):
        with patch.object(joint.long_audit, "audit_long", side_effect=ValueError("pair incomplete")):
            with self.assertRaisesRegex(ValueError, "pair incomplete"):
                joint.audit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
