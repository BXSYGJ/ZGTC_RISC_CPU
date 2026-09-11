import copy
import unittest

from check_frequency_candidate import assess_candidate
from check_performance_target import assess
from test_performance_target import fixture


def candidate():
    case = fixture()
    case["result"].update(iterations=3906, cycles=1260000000, clock_hz=126000000)
    case["manifest"]["ClockHz"] = case["report"]["clock_hz"] = 126000000
    case["report"]["resources"]["post_route_luts"] = 12600
    case["source_snapshot_verified"] = True
    return case


class FrequencyCandidateTests(unittest.TestCase):
    def test_joint_threshold_without_mutating_evidence(self):
        case = candidate()
        original = copy.deepcopy(case)
        result = assess_candidate(case, 126000000)
        self.assertEqual(result["status"], "numeric_target_pass")
        self.assertAlmostEqual(result["measured"]["coremark_per_lut"], 0.031)
        self.assertEqual(result["target"]["clock_hz"], 126000000)
        self.assertEqual(result["target"]["coremark"], 378)
        self.assertTrue(result["gates"]["clock_exactly_126000000hz"])
        self.assertFalse(result["physical_limits_proven"])
        self.assertFalse(result["board_identity_verified_by_this_tool"])
        self.assertEqual(case, original)

    def test_fixed_gate_remains_fixed_and_requested_clock_is_not_inferred(self):
        case = candidate()
        self.assertEqual(assess(case)["status"], "target_not_met")
        self.assertFalse(assess(case)["gates"]["clock_exactly_120mhz"])
        self.assertEqual(assess_candidate(case, 135000000)["status"], "target_not_met")
        baseline = fixture()
        baseline["source_snapshot_verified"] = True
        self.assertEqual(assess_candidate(baseline, 126000000)["status"], "target_not_met")

    def test_invalid_requested_frequency_and_unverified_snapshot(self):
        for frequency in (True, 126000000.0, 0, 119999999):
            with self.subTest(frequency=frequency), self.assertRaises(ValueError):
                assess_candidate(candidate(), frequency)
        for verified in (False, None, 1):
            case = candidate()
            case["source_snapshot_verified"] = verified
            with self.subTest(verified=verified), self.assertRaises(ValueError):
                assess_candidate(case, 126000000)

    def test_exact_resource_floor_and_one_lut_over(self):
        case = candidate()
        case["report"]["resources"]["post_route_luts"] += 1
        result = assess_candidate(case, 126000000)
        self.assertFalse(result["gates"]["resource_at_least_0_031_coremark_per_lut"])
        self.assertEqual(result["status"], "target_not_met")

    def test_execution_floor_and_one_cycle_over(self):
        case = candidate()
        case["result"]["iterations"] = 3780
        case["report"]["resources"]["post_route_luts"] = 12000
        self.assertEqual(assess_candidate(case, 126000000)["status"], "numeric_target_pass")
        case["result"]["cycles"] += 1
        result = assess_candidate(case, 126000000)
        self.assertFalse(result["gates"]["execution_at_least_3_coremark_per_mhz"])
        self.assertEqual(result["status"], "target_not_met")

    def test_higher_frequency_does_not_bypass_other_gates(self):
        mutations = (("result", "cycles", 1259999999), ("result", "reportable_duration", False),
                     ("result", "validation_run", True), ("result", "seed_crc", "18f2"),
                     ("result", "crc_valid", False), ("report", "constraints_met", False),
                     ("manifest", "TimingConstraintsMet", False), ("manifest", "Device", "other"))
        for group, field, value in mutations:
            case = candidate()
            case[group][field] = value
            with self.subTest(field=field):
                self.assertEqual(assess_candidate(case, 126000000)["status"], "target_not_met")
        case = candidate()
        case["manifest"]["ClockHz"] = 120000000
        with self.assertRaises(ValueError):
            assess_candidate(case, 126000000)


if __name__ == "__main__":
    unittest.main()
