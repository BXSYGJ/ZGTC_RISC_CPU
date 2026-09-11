import os
from pathlib import Path
import subprocess
import tempfile
import unittest


VERILATED_STUB = "#pragma once\n#include <cstdint>\nusing vluint64_t = uint64_t;\nextern bool fake_finish;\nclass Verilated {\npublic:\n    static void commandArgs(int, char**) {}\n    static bool gotFinish() { return fake_finish; }\n};\n"
MODEL_STUB = "#pragma once\n#include <cstdint>\n#include <cstdlib>\nbool fake_finish = false;\nclass Vrv32_soc {\n    bool previous_clock = false;\n    uint64_t cycle = 0;\n    int mode = std::atoi(std::getenv(\"HARNESS_TEST_MODE\"));\npublic:\n    uint8_t clk=0, rst_n=0, serial_rx=1, gpio_input=0, serial_tx=1;\n    uint32_t status_code=0, trace_pc=0, trap_cause=0;\n    uint8_t trap_valid=0, maintenance_fault=0;\n    uint64_t retired_count=42;\n    void final() {}\n    void eval() {\n        if (!rst_n) { cycle=0; status_code=0; previous_clock=clk; return; }\n        if (clk && !previous_clock) {\n            ++cycle;\n            if (mode != 1 && mode != 7 && cycle >= 2) status_code=0xc0100000U;\n            if (mode == 2 && cycle == 10) trap_valid=1;\n            if (mode == 3 && cycle == 10) maintenance_fault=1;\n            if (mode == 8 && cycle == 20) fake_finish=true;\n            if (mode == 7) status_code=0xc0100001U;\n            if (mode != 1 && cycle >= 400 && cycle < 720) {\n                const uint64_t elapsed = cycle - 400;\n                if (elapsed < 32) serial_tx = mode == 4 && elapsed >= 4;\n                else if (elapsed < 288) serial_tx = (0x4bU >> (elapsed / 32 - 1)) & 1U;\n                else serial_tx = mode != 5;\n            } else serial_tx=1;\n            if (mode == 6 && cycle == 430) status_code=0xc0100001U;\n            if (mode != 1 && cycle >= 750) status_code=0xc0100001U;\n            if (mode == 0 && cycle >= 3 && cycle <= 290) {\n                const uint64_t elapsed=cycle-3;\n                const unsigned expected=elapsed<32 ? 0 : (elapsed<288 ? ((0x47U >> (elapsed/32-1))&1U) : 1);\n                if (serial_rx != expected) trap_valid=1;\n            }\n        }\n        previous_clock=clk;\n    }\n};\n"


class CompiledHarnessControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.addClassCleanup(cls.temporary.cleanup)
        (cls.root / "verilated.h").write_text(VERILATED_STUB, encoding="utf-8")
        (cls.root / "Vrv32_soc.h").write_text(MODEL_STUB, encoding="utf-8")
        cls.driver = Path(__file__).resolve().parents[1] / "sim" / "coremark_compiled.cpp"
        cls.binary = cls.root / "harness"
        subprocess.run(["/usr/bin/g++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                        "-I", str(cls.root), str(cls.driver), "-o", str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_harness(self, mode, limit="1000"):
        output = self.root / f"uart-{mode}.txt"
        result = subprocess.run([str(self.binary), str(output), limit],
                                env={**os.environ, "HARNESS_TEST_MODE": str(mode)},
                                capture_output=True, text=True, timeout=5)
        return result, output

    def test_actual_driver_uart_and_command(self):
        result, output = self.run_harness(0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS compiled RTL simulation", result.stdout)
        self.assertEqual(output.read_text(encoding="ascii"), "ZGTC RTL_SIMULATION_ONLY\nK")

    def test_actual_driver_error_guards(self):
        cases = {1: "cycle limit exceeded", 2: "trap or maintenance fault",
                 3: "trap or maintenance fault", 4: "start bit invalid",
                 5: "stop bit invalid", 6: "Incomplete CoreMark UART transaction",
                 7: "Incomplete CoreMark UART transaction", 8: "Unexpected RTL finish"}
        for mode, expected in cases.items():
            with self.subTest(mode=mode):
                result, _ = self.run_harness(mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("PASS compiled RTL simulation", result.stdout)

    def test_actual_driver_argument_guards(self):
        for limit in ("0", "-1", "bad", "1000000000001", "99999999999999999999999"):
            with self.subTest(limit=limit):
                result, _ = self.run_harness(0, limit)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL", result.stderr)
        result = subprocess.run([str(self.binary)], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected UART output path", result.stderr)


if __name__ == "__main__":
    unittest.main()
