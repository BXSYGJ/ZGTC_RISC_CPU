import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from analyze_branch_history import analyze
import test_coremark_compiled_harness as harness


PROJECT = Path(__file__).resolve().parents[1]
PROFILE_FIELDS = """
    uint8_t trace_valid=0;
    uint8_t rv32_soc__DOT__core__DOT__mem_fire=0;
    uint8_t rv32_soc__DOT__core__DOT__mem_fence_i=0;
    uint8_t rv32_soc__DOT__core__DOT__mem_branch=0;
    uint8_t rv32_soc__DOT__core__DOT__mem_fault=0;
    uint32_t rv32_soc__DOT__core__DOT__mem_pc=0x100;
    uint32_t rv32_soc__DOT__core__DOT__mem_instruction=0x08000063;
    uint32_t rv32_soc__DOT__core__DOT__mem_target=0x180;
    uint32_t rv32_soc__DOT__core__DOT__mem_next_pc=0x180;
    uint32_t rv32_soc__DOT__core__DOT__mem_prediction=0x104;
    uint8_t rv32_soc__DOT__core__DOT__mem_taken=1;
    uint8_t rv32_soc__DOT__core__DOT__mem_conditional=1;
"""
PROFILE_FALLING_EDGE = """
        if (clk && !previous_clock) {
            trace_valid=0;
            rv32_soc__DOT__core__DOT__mem_fire=0;
            rv32_soc__DOT__core__DOT__mem_branch=0;
        }
        if (!clk && previous_clock && rst_n) {
            trace_valid=0;
            rv32_soc__DOT__core__DOT__mem_fire=0;
            rv32_soc__DOT__core__DOT__mem_branch=0;
            if (cycle==100 && mode!=9) { trace_valid=1; trace_pc=0x1398; }
            if (cycle==200 && mode!=10) { trace_valid=1; trace_pc=0x5a88; }
            if (cycle==150 && mode==11) { trace_valid=1; trace_pc=0x1398; }
            if ((cycle==50 || cycle==150 || cycle==250) && mode!=12) {
                rv32_soc__DOT__core__DOT__mem_fire=mode!=15;
                rv32_soc__DOT__core__DOT__mem_branch=mode!=16;
                rv32_soc__DOT__core__DOT__mem_fault=mode==14;
                if (cycle==150 && mode!=11) { trace_valid=1; trace_pc=0x100; }
            }
            if (mode==13 && cycle==160) {
                rv32_soc__DOT__core__DOT__mem_fire=1;
                rv32_soc__DOT__core__DOT__mem_fence_i=1;
            }
        }
"""


class BranchProfileHarnessControls(harness.CompiledHarnessControls):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="branch-profile-harness-")
        cls.root = Path(cls.temporary.name)
        cls.addClassCleanup(cls.temporary.cleanup)
        (cls.root / "verilated.h").write_text(harness.VERILATED_STUB, encoding="utf-8")
        model = harness.MODEL_STUB.replace("    uint32_t status_code=", PROFILE_FIELDS + "    uint32_t status_code=")
        model = model.replace("        previous_clock=clk;", PROFILE_FALLING_EDGE + "        previous_clock=clk;")
        (cls.root / "Vrv32_soc.h").write_text(model, encoding="utf-8")
        cls.driver = PROJECT / "experiments/btb_history_profile/coremark_compiled.cpp"
        cls.binary = cls.root / "harness"
        subprocess.run(["/usr/bin/g++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                        "-I", str(cls.root), str(cls.driver), "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def test_actual_driver_uart_and_command(self):
        result, output = self.run_harness(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS compiled RTL simulation", result.stdout)
        self.assertEqual(output.read_text(encoding="ascii"), "ZGTC RTL_SIMULATION_ONLY\nK")
        trace = Path(str(output) + ".branches.csv")
        rows = trace.read_text(encoding="ascii").splitlines()
        self.assertEqual(rows[2:5], [
            "50,0,00000100,08000063,00000180,00000180,00000104,1,1",
            "150,1,00000100,08000063,00000180,00000180,00000104,1,1",
            "250,0,00000100,08000063,00000180,00000180,00000104,1,1",
        ])
        self.assertEqual(rows[-1], "END,3,100,2")
        self.assertEqual(analyze(trace.read_text(encoding="ascii"))["total_records"], 3)

    def test_profile_window_and_qualification_guards(self):
        cases = {9: "Incomplete branch profile window", 10: "Incomplete branch profile window",
                 11: "Repeated iterate entry", 12: "Incomplete branch profile window",
                 13: "does not support dynamic predictor invalidation",
                 14: "Incomplete branch profile window", 15: "Incomplete branch profile window",
                 16: "Incomplete branch profile window"}
        for mode, expected in cases.items():
            with self.subTest(mode=mode):
                result, output = self.run_harness(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("PASS compiled RTL simulation", result.stdout)
                self.assertNotIn("END,", Path(str(output) + ".branches.csv").read_text(encoding="ascii"))

    def test_branch_output_open_and_flush_failures(self):
        for name, expected in (("directory", "Cannot open branch trace output"),
                               ("full", "Branch trace write failed")):
            with self.subTest(name=name):
                output = self.root / (name + ".uart")
                trace = Path(str(output) + ".branches.csv")
                if name == "directory":
                    trace.mkdir()
                else:
                    trace.symlink_to("/dev/full")
                result = subprocess.run([str(self.binary), str(output), "1000"],
                                        env={**os.environ, "HARNESS_TEST_MODE": "0"},
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("PASS compiled RTL simulation", result.stdout)


if __name__ == "__main__":
    unittest.main()
