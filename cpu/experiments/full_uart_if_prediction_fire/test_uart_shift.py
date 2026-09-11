import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
ROOT = EXPERIMENT.parents[1]
BASELINE = ROOT / "build/regfile-valid-fanout-stage/rtl"
RESULTS = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class UartShiftTests(unittest.TestCase):
    def test_source_scope(self):
        self.assertEqual(digest(BASELINE / "rv32_core.sv"),
                         "dc90363d426754f032ec04db6f4be76da439cca149e372853ee2d64536d20fce")
        for reference in BASELINE.glob("*.sv"):
            candidate = EXPERIMENT / "rtl" / reference.name
            if reference.name != "rv32_uart.sv":
                self.assertEqual(reference.read_bytes(), candidate.read_bytes(), reference.name)
        original = (BASELINE / "rv32_uart.sv").read_text(encoding="utf-8-sig")
        changed = original.replace("rx_shift[rx_bit]<=rx_sync;", "rx_shift<={rx_sync,rx_shift[7:1]};")
        self.assertNotEqual(original, changed)
        self.assertEqual(changed, (EXPERIMENT / "rtl/rv32_uart.sv").read_text(encoding="utf-8-sig"))

    def simulate(self, top, clock_hz=None, baud=None, mutation=False):
        candidate = (EXPERIMENT / "rtl/rv32_uart.sv").read_text(encoding="utf-8-sig")
        if mutation:
            self.assertIn("rx_shift<={rx_sync,rx_shift[7:1]};", candidate)
            candidate = candidate.replace("rx_shift<={rx_sync,rx_shift[7:1]};",
                                          "rx_shift<={rx_shift[6:0],rx_sync};")
        reference = (BASELINE / "rv32_uart.sv").read_text(encoding="utf-8-sig")
        reference = reference.replace("module rv32_uart #(", "module rv32_uart_reference #(", 1)
        with tempfile.TemporaryDirectory(prefix="uart-shift-") as temporary:
            work = Path(temporary)
            files = {"candidate.sv": candidate, "reference.sv": reference}
            for name in ("rv32_fifo.sv", "rv32_peripherals.sv"):
                files[name] = (EXPERIMENT / "rtl" / name).read_text(encoding="utf-8-sig")
            bench = EXPERIMENT / "uart_equivalence_tb.sv" if top == "uart_equivalence_tb" else ROOT / "sim" / (top + ".sv")
            files["bench.sv"] = bench.read_text(encoding="utf-8-sig")
            for name, text in files.items():
                (work / name).write_text(text, encoding="utf-8")
            binary = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", top, "-o", str(binary)]
            if clock_hz is not None:
                command += [f"-P{top}.CLOCK_HZ={clock_hz}", f"-P{top}.BAUD={baud}"]
            compiled = subprocess.run(command + [str(work / name) for name in files],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(binary)], capture_output=True, text=True, timeout=180)
            RESULTS.append({"top": top, "clock_hz": clock_hz, "baud": baud,
                            "mutation": mutation, "returncode": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
            print(result.stdout, end="", flush=True)
            return result

    def test_cycle_equivalence(self):
        for clock, baud in ((3200, 100), (157500000, 115200)):
            with self.subTest(clock=clock):
                result = self.simulate("uart_equivalence_tb", clock, baud)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS uart_equivalence", result.stdout)

    def test_negative_shift_direction(self):
        result = self.simulate("uart_equivalence_tb", 3200, 100, mutation=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UART_MISMATCH", result.stdout)

    def test_existing_uart(self):
        result = self.simulate("uart_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_full_peripherals(self):
        result = self.simulate("peripherals_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS peripherals", result.stdout)


if __name__ == "__main__":
    outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UartShiftTests))
    build = EXPERIMENT / "build"
    build.mkdir(exist_ok=True)
    receipt = {"schema": 1, "simulation_passed": outcome.wasSuccessful(),
               "physical_validated": False, "hardware_coremark_validated": False,
               "source_sha256": {path.name: digest(path) for path in sorted((EXPERIMENT / "rtl").glob("*.sv"))},
               "test_sha256": digest(Path(__file__)), "bench_sha256": digest(EXPERIMENT / "uart_equivalence_tb.sv"),
               "runs": RESULTS}
    (build / "regression.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(not outcome.wasSuccessful())
