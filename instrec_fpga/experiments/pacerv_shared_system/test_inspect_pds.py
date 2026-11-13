"""Ensure a completed PDS flow cannot hide failing or missing timing checks."""
import unittest

from inspect_pds import clock_contract, timing_summary


def fixture():
    tables = []
    for corner in ("Slow", "Fast"):
        for check in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"):
            clock = "core" if check == "Minimum Pulse Width" else "core core"
            tables.append(f"{check} Summary({corner} Corner):\n****\n{clock} 0.004 0.000 0 25\n=====\n")
    return "Design Summary : All Constraints Met.\n" + "".join(tables)


class TimingGate(unittest.TestCase):
    def test_all_ten_summaries_required(self):
        self.assertTrue(timing_summary(fixture())["all_constraints_met"])
        self.assertFalse(timing_summary(fixture().split("Minimum Pulse Width Summary(Fast")[0])["all_constraints_met"])

    def test_each_corner_and_check_can_reject(self):
        for heading in (f"{check} Summary({corner} Corner):" for corner in ("Slow", "Fast")
                        for check in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width")):
            with self.subTest(heading=heading):
                prefix, suffix = fixture().split(heading)
                failing = prefix + heading + suffix.replace("0.004 0.000 0 25", "-0.001 -0.001 1 25", 1)
                self.assertFalse(timing_summary(failing)["all_constraints_met"])

    def test_design_summary_must_also_pass(self):
        self.assertFalse(timing_summary(fixture().replace("All Constraints Met", "Some Constraints Violated"))["all_constraints_met"])


class ClockGate(unittest.TestCase):
    manifest = {"system_clock_hz": 109375000, "pixel_clock_hz": 148500000}

    def test_requested_clock_and_print_rounding(self):
        text = " ddrphy_sysclk 109.3750 MHz 115.0000 MHz\n pix_clk 148.5001 MHz 160.0000 MHz\n"
        self.assertTrue(clock_contract(text, self.manifest)["passed"])

    def test_estimated_clock_cannot_replace_requested_clock(self):
        text = " ddrphy_sysclk 125.0000 MHz 109.3750 MHz\n pix_clk 148.5001 MHz 160.0000 MHz\n"
        self.assertFalse(clock_contract(text, self.manifest)["passed"])

    def test_missing_pixel_clock_rejects_complete_system(self):
        self.assertFalse(clock_contract(" ddrphy_sysclk 109.3750 MHz 115.0000 MHz\n", self.manifest)["passed"])


if __name__ == "__main__":
    unittest.main()
