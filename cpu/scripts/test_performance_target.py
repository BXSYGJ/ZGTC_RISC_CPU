import copy
import unittest

from check_performance_target import assess


def fixture():
    return {"result": {"iterations": 3600, "cycles": 1200000000, "retired": 900000000,
                       "clock_hz": 120000000, "reportable_duration": True, "validation_run": False,
                       "seed_crc": "e9f5", "crc_valid": True},
            "report": {"clock_hz": 120000000, "constraints_met": True,
                       "resources": {"post_route_luts": 5000}},
            "manifest": {"ClockHz": 120000000, "TimingConstraintsMet": True,
                         "Device": "PG2L200H-6FBB676"}}


class PerformanceTargetTests(unittest.TestCase):
    def test_exact_threshold_and_all_metrics(self):
        report = assess(fixture())
        self.assertEqual(report["status"], "numeric_target_pass")
        self.assertEqual(report["measured"]["coremark"], 360)
        self.assertEqual(report["measured"]["coremark_per_mhz"], 3)
        self.assertEqual(report["measured"]["coremark_per_lut"], 0.072)
        self.assertFalse(report["physical_limits_proven"])

    def test_one_extra_cycle_cannot_round_up_to_pass(self):
        case = fixture()
        case["result"]["cycles"] += 1
        self.assertEqual(assess(case)["status"], "target_not_met")

    def test_higher_clock_not_substituted(self):
        case = fixture()
        case["result"]["clock_hz"] = case["manifest"]["ClockHz"] = case["report"]["clock_hz"] = 162000000
        self.assertFalse(assess(case)["gates"]["clock_exactly_120mhz"])

    def test_short_and_validation_and_bad_crc_rejected(self):
        for key, value in (("reportable_duration", False), ("validation_run", True),
                           ("seed_crc", "18f2"), ("crc_valid", False), ("cycles", 1199999999)):
            with self.subTest(key=key):
                case = fixture()
                case["result"][key] = value
                self.assertEqual(assess(case)["status"], "target_not_met")

    def test_timing_or_device_failure(self):
        for group, key, value in (("report", "constraints_met", False),
                                  ("manifest", "TimingConstraintsMet", False),
                                  ("manifest", "Device", "other")):
            case = fixture()
            case[group][key] = value
            self.assertEqual(assess(case)["status"], "target_not_met")

    def test_invalid_counters_and_clock_disagreement(self):
        for key in ("cycles", "iterations", "retired", "clock_hz"):
            for value in (0, -1, True, 1.0):
                case = fixture()
                case["result"][key] = value
                with self.assertRaises(ValueError):
                    assess(case)
        case = fixture()
        case["manifest"]["ClockHz"] = 162000000
        with self.assertRaises(ValueError):
            assess(case)

    def test_instruction_count_bound_is_explicitly_conditional(self):
        case = fixture()
        case["result"].update(iterations=1000, cycles=1927984580, retired=752528394)
        original = copy.deepcopy(case)
        report = assess(case)
        self.assertAlmostEqual(report["diagnostic"]["required_average_ipc_with_unchanged_instruction_count"], 2.257585182)
        self.assertAlmostEqual(report["diagnostic"]["single_retire_per_cycle_unchanged_code_upper_bound_coremark_per_mhz"], 1.328853511, places=7)
        self.assertEqual(case, original)


if __name__ == "__main__":
    unittest.main()
