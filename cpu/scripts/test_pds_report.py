import unittest
from pds_report import parse_reports


TIMING = """| Device : PG2L200H
| Speed Grade : -6
| Package : FBB676
clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred 9.2590 {0 4.629} Generated (clk) 3309 301 {pll}
clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred
108.0030 MHz 118.5115 MHz 9.2590 8.4380 0.821
Design Summary : All Constraints Met.
"""
LOG = """Total LUTs: 4171 of 159800
Device Utilization Summary :
| Use of CLMA | 1255 | 30075 |
|   FF       | 2764 | 240600 |
|   LUT      | 3437 | 120300 |
| Use of CLMS | 390 | 9875 |
|   FF       | 733 | 79000 |
|   LUT      | 1114 | 39500 |
|   Distributed RAM | 324 | 39500 |
| Use of DRM | 16.5 | 415 |
| Use of GPLL | 1 | 10 |
SCBV has not been set
"""


class PdsReportTests(unittest.TestCase):
    def test_distinct_resource_stages(self):
        result = parse_reports(TIMING, LOG, 108000000)
        self.assertTrue(result["constraints_met"])
        self.assertEqual(result["resources"]["synthesis_luts"], 4171)
        self.assertEqual(result["resources"]["post_route_luts"], 4551)
        self.assertEqual(result["resources"]["post_route_ffs"], 3497)
        self.assertTrue(result["scbv_unset_warning"])

    def test_timing_failure_is_not_success(self):
        result = parse_reports(TIMING.replace("All Constraints Met.", "Some Constraints Not Met."), LOG, 108000000)
        self.assertFalse(result["constraints_met"])

    def test_clock_mismatch(self):
        for clock in (0, 99000000, 135000000):
            with self.subTest(clock=clock), self.assertRaises(ValueError):
                parse_reports(TIMING, LOG, clock)

    def test_direct_reference_clock(self):
        timing = TIMING.replace("clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred", "clk")
        timing = timing.replace("9.2590", "37.0370").replace("Generated (clk)", "Declared")
        timing = timing.replace("108.0030 MHz", "27.0000 MHz")
        result = parse_reports(timing, LOG.replace("| Use of GPLL | 1", "| Use of GPLL | 0"), 27000000)
        self.assertEqual(result["resources"]["GPLL"], 0)

    def test_missing_duplicate_and_invalid_fields(self):
        cases = [(TIMING.replace("PG2L200H", "PG2L100H"), LOG),
                 (TIMING.replace("108.0030 MHz", "270.0000 MHz"), LOG),
                 (TIMING.replace("0.821", "-0.821"), LOG),
                 (TIMING.replace("9.2590 8.4380", "10.0000 8.4380"), LOG),
                 (TIMING.replace("3309 301", "0 301"), LOG),
                 (TIMING + "Design Summary : All Constraints Met.\n", LOG),
                 (TIMING, LOG.replace("Device Utilization Summary :", "missing")),
                 (TIMING, LOG.replace("|   LUT      | 1114 | 39500 |", "")),
                 (TIMING, LOG.replace("| Use of GPLL | 1", "| Use of GPLL | 0")),
                 (TIMING, LOG + "Total LUTs: 100 of 159800\n")]
        for timing, log in cases:
            with self.subTest(timing=timing, log=log), self.assertRaises(ValueError):
                parse_reports(timing, log, 108000000)


if __name__ == "__main__":
    unittest.main()
