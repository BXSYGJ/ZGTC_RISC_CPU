import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "build/regfile-valid-fanout-stage/rtl"
EXPERIMENT = Path(__file__).resolve().parent


class FullPeripheralsTests(unittest.TestCase):
    def setUp(self):
        original = BASELINE / "rv32_peripherals.sv"
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
                         "b61ed1bc98ca4b6375aa27337fb6c68091fbfeba156495424d71431a6f4630e6")
        self.reference = original.read_text(encoding="utf-8-sig")
        candidate = EXPERIMENT / "rv32_peripherals.sv"
        self.assertFalse(candidate.read_bytes().startswith(bytes.fromhex("efbbbf")), "Verilog input must not contain a BOM")
        self.candidate = candidate.read_text(encoding="utf-8")

    def simulate(self, bench, mutation=None):
        candidate = self.candidate
        if mutation:
            before, after = mutation
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="full-peripherals-") as temporary:
            work = Path(temporary)
            inputs = {"candidate.sv": candidate,
                      "reference.sv": self.reference.replace("module rv32_peripherals #(",
                                                               "module rv32_peripherals_parent #(", 1),
                      "fifo.sv": (BASELINE / "rv32_fifo.sv").read_text(encoding="utf-8-sig"),
                      "uart.sv": (BASELINE / "rv32_uart.sv").read_text(encoding="utf-8-sig"),
                      "bench.sv": (ROOT / "sim" / (bench + ".sv")).read_text(encoding="utf-8-sig")}
            for name, text in inputs.items():
                (work / name).write_text(text, encoding="utf-8")
            executable = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", bench, "-o", str(executable),
                                       *[str(work / name) for name in inputs]],
                                      capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=120)

    def test_only_four_synthesis_attributes_change(self):
        attribute = "(* syn_keep=1 *) "
        count = self.reference.count(attribute)
        stripped = self.reference.replace(attribute, "")
        self.assertEqual(count, 4)
        self.assertEqual(self.candidate, stripped)

    def test_full_mmio_gpio_uart_timer_snapshot(self):
        result = self.simulate("peripherals_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS peripherals", result.stdout)
        print(result.stdout, end="", flush=True)

    def test_timer_cycle_equivalence(self):
        result = self.simulate("timer_irq_next_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS timer_irq_next", result.stdout)
        print(result.stdout, end="", flush=True)

    def test_full_function_negative_controls(self):
        mutations = [
            ("gpio_output<=(gpio_output & ~write_mask[7:0]) | (req_data[7:0] & write_mask[7:0]);",
             "gpio_output<=gpio_output;"),
            (".serial_rx(serial_rx)", ".serial_rx(1'b1)"),
            ("performance_snapshot<=performance_values;", "performance_snapshot<=0;"),
            ("timer_incremented=timer_value+1'b1;", "timer_incremented=timer_value;")]
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                result = self.simulate("peripherals_tb", mutation)
                self.assertNotEqual(result.returncode, 0, "Regression was not detected")
                self.assertIn("FATAL:", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
