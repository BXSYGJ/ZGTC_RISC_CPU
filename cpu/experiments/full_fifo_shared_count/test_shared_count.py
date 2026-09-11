import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
ROOT = EXPERIMENT.parents[1]
BASELINE = ROOT / "build/regfile-valid-fanout-stage"
RUNS = []
BEFORE = "                2'b10: count<=count+1'b1;\n                2'b01: count<=count-1'b1;"
AFTER = "                2'b10,2'b01: count<=count+{{DEPTH_BITS{pop}},1'b1};"


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


class SharedCountTests(unittest.TestCase):
    def test_exact_source_delta(self):
        self.assertEqual(digest(EXPERIMENT / "rtl/rv32_core.sv"), "dc90363d426754f032ec04db6f4be76da439cca149e372853ee2d64536d20fce")
        for directory in ("rtl", "fpga", "constraints"):
            expected = {item.relative_to(BASELINE / directory) for item in (BASELINE / directory).rglob("*") if item.is_file()}
            actual = {item.relative_to(EXPERIMENT / directory) for item in (EXPERIMENT / directory).rglob("*") if item.is_file()}
            self.assertEqual(expected, actual)
            for relative in expected:
                if directory == "rtl" and relative.name == "rv32_fifo.sv":
                    continue
                self.assertEqual((BASELINE / directory / relative).read_bytes(), (EXPERIMENT / directory / relative).read_bytes())
        original = (BASELINE / "rtl/rv32_fifo.sv").read_text(encoding="utf-8-sig")
        self.assertEqual(original.count(BEFORE), 1)
        self.assertEqual(original.replace(BEFORE, AFTER), (EXPERIMENT / "rtl/rv32_fifo.sv").read_text(encoding="utf-8-sig"))

    def simulate(self, top, width=8, depth=4, mutation=None):
        candidate = (EXPERIMENT / "rtl/rv32_fifo.sv").read_text(encoding="utf-8-sig")
        label = "positive"
        if mutation:
            label, before, after = mutation
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        reference = (BASELINE / "rtl/rv32_fifo.sv").read_text(encoding="utf-8-sig").replace("module rv32_fifo #(", "module rv32_fifo_reference #(", 1)
        bench = EXPERIMENT / "fifo_equivalence_tb.sv" if top == "fifo_equivalence_tb" else EXPERIMENT / "sim" / (top + ".sv")
        with tempfile.TemporaryDirectory(prefix="fifo-shared-count-") as temporary:
            work = Path(temporary)
            files = {"candidate.sv": candidate, "reference.sv": reference, "bench.sv": bench.read_text(encoding="utf-8-sig")}
            if top == "peripherals_tb":
                for name in ("rv32_uart.sv", "rv32_peripherals.sv"):
                    files[name] = (EXPERIMENT / "rtl" / name).read_text(encoding="utf-8-sig")
            for name, text in files.items():
                (work / name).write_text(text, encoding="utf-8")
            binary = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", top, "-o", str(binary)]
            if top == "fifo_equivalence_tb":
                command += [f"-P{top}.WIDTH={width}", f"-P{top}.DEPTH_BITS={depth}"]
            result = subprocess.run(command + [str(work / name) for name in files], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run(["vvp", str(binary)], capture_output=True, text=True, timeout=60)
            RUNS.append({"label": label, "top": top, "width": width, "depth_bits": depth, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            print(label + ": " + result.stdout.strip(), flush=True)
            return result

    def test_equivalence(self):
        for width, depth in ((1, 1), (8, 2), (8, 4), (32, 6)):
            with self.subTest(width=width, depth=depth):
                result = self.simulate("fifo_equivalence_tb", width, depth)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("cycles=32768", result.stdout)

    def test_existing_queue_model(self):
        result = self.simulate("fifo_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS fifo checks=", result.stdout)

    def test_full_peripherals(self):
        result = self.simulate("peripherals_tb")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS peripherals checks=", result.stdout)

    def test_runtime_mutants(self):
        mutations = (
            ("wrong_sign", "{{DEPTH_BITS{pop}},1'b1}", "{{DEPTH_BITS{push}},1'b1}"),
            ("missing_decrement", "{{DEPTH_BITS{pop}},1'b1}", "1'b1"),
            ("wrong_low_bit", "{{DEPTH_BITS{pop}},1'b1}", "{{DEPTH_BITS{pop}},1'b0}"),
            ("exchange_count", "2'b10,2'b01:", "2'b10,2'b01,2'b11:"),
            ("full_exchange_blocked", "count!=(1<<DEPTH_BITS) || pop", "count!=(1<<DEPTH_BITS)"),
            ("wrong_write_pointer", "write_pointer+1'b1", "write_pointer-1'b1"),
        )
        for mutation in mutations:
            with self.subTest(label=mutation[0]):
                result = self.simulate("fifo_equivalence_tb", mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FIFO_MISMATCH", result.stdout)


if __name__ == "__main__":
    outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SharedCountTests))
    build = EXPERIMENT / "build"
    build.mkdir(exist_ok=True)
    files = sorted((EXPERIMENT / "rtl").glob("*.sv")) + [Path(__file__), EXPERIMENT / "fifo_equivalence_tb.sv", EXPERIMENT / "sim/fifo_tb.sv", EXPERIMENT / "sim/peripherals_tb.sv"]
    receipt = {"simulation_passed": outcome.wasSuccessful(), "runs": RUNS, "sha256": {str(filename.relative_to(EXPERIMENT)): digest(filename) for filename in files}, "hardware_validated": False}
    (build / "fifo-regression.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(not outcome.wasSuccessful())
