import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
CPU = ROOT.parents[1]
RECEIPT = json.loads((ROOT / "change-receipt.json").read_text(encoding="utf-8"))
OUTPUT = ROOT / "build" / ("functional-" + uuid4().hex[:8])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class TimerPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=False)
        cls.case_number = 0

    def test_exact_source_delta(self):
        original = BASE / "rtl/rv32_peripherals.sv"
        candidate = ROOT / "rv32_peripherals.sv"
        self.assertEqual(digest(original), RECEIPT["parent_sha256"])
        self.assertEqual(digest(candidate), RECEIPT["candidate_sha256"])
        expected = original.read_text(encoding="utf-8")
        self.assertEqual(len(RECEIPT["substitutions"]), 1)
        for before, after in RECEIPT["substitutions"]:
            self.assertEqual(expected.count(before), 1)
            expected = expected.replace(before, after)
        self.assertEqual(candidate.read_text(encoding="utf-8"), expected)
        self.assertEqual(len(RECEIPT["read_addresses"]), 26)
        self.assertEqual(len(set(RECEIPT["read_addresses"])), 26)

    def simulate(self, mutation=None):
        TimerPrefixTests.case_number += 1
        stage = OUTPUT / ("case-" + str(TimerPrefixTests.case_number))
        stage.mkdir()
        candidate = (ROOT / "rv32_peripherals.sv").read_text(encoding="utf-8")
        if mutation:
            before, after = mutation
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        reference = (BASE / "rtl/rv32_peripherals.sv").read_text(encoding="utf-8")
        self.assertEqual(reference.count("module rv32_peripherals #("), 1)
        reference = reference.replace("module rv32_peripherals #(", "module rv32_peripherals_reference #(")
        bench = (CPU / "sim/peripherals_tb.sv").read_text(encoding="utf-8")
        anchor = "    integer checks=0,request_waits=0;"
        self.assertEqual(bench.count(anchor), 1)
        bench = bench.replace(anchor, (ROOT / "timer_observer.sv.in").read_text(encoding="utf-8") + anchor)
        anchor = '        $display("PASS peripherals checks=%0d request_waits=%0d",checks,request_waits);'
        self.assertEqual(bench.count(anchor), 1)
        bench = bench.replace(anchor, "        exercise_banked_addresses();\n        exercise_timer_prefix();\n" + anchor)
        sources = {"candidate.sv": candidate, "reference.sv": reference, "testbench.sv": bench}
        for name, source in sources.items():
            (stage / name).write_text(source, encoding="utf-8")
        inputs = [stage / name for name in sources] + [BASE / "rtl/rv32_fifo.sv", BASE / "rtl/rv32_uart.sv"]
        image = stage / "test.vvp"
        command = ["iverilog", "-g2012", "-s", "peripherals_tb", "-o", str(image), *map(str, inputs)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (stage / "compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        self.assertEqual(compiled.stdout, "")
        for line in compiled.stderr.splitlines():
            warning = re.fullmatch(r"(.+):([0-9]+): warning: Attributes are not supported on net declaration assignments and will be discarded\.", line)
            self.assertIsNotNone(warning, line)
            path = Path(warning[1])
            self.assertIn(path, inputs)
            declaration = path.read_text(encoding="utf-8").splitlines()[int(warning[2]) - 1]
            self.assertIn("(*", declaration)
            self.assertIn("wire", declaration)
        executed = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=180)
        output = executed.stdout + executed.stderr
        (stage / "execute.log").write_text(output, encoding="utf-8")
        (stage / "invocation.json").write_text(json.dumps({"compile_command": command, "compile_exit": compiled.returncode,
            "execute_exit": executed.returncode, "mutation": mutation,
            "inputs": {str(path): digest(path) for path in inputs}, "executable_sha256": digest(image)}, indent=2) + "\n", encoding="utf-8")
        if mutation:
            self.assertNotEqual(executed.returncode, 0, output)
            self.assertRegex(output, "FAIL (banked differential|peripherals)")
        else:
            self.assertEqual(executed.returncode, 0, output)
            self.assertIn("PASS peripherals", output)
            self.assertIn("exhaustive_low_addresses=2048 high_bit_alias_reads=10752 snapshots=16", output)
            self.assertRegex(output, r"PASS timer prefix boundaries=57 partial_writes=512 carry16=[1-9][0-9]* carry32=[1-9][0-9]* carry48=[1-9][0-9]* wrap64=[1-9][0-9]*")
        print(output.strip(), flush=True)

    def test_complete_peripherals_timer_boundaries_and_address_space(self):
        self.simulate()

    def test_compiled_timer_faults_rejected(self):
        mutations = (
            ("timer_value[15:0]+16'd1", "timer_value[15:0]+16'd0"),
            ("timer_chunk*16-1:0", "timer_chunk*16-2:0"),
            ("timer_value[timer_chunk*16+:16]+", "16'd0+"),
            ("irq_timer<=timer_interrupt_next;", "irq_timer<=1'b0;"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate(mutation)


if __name__ == "__main__":
    originals = [ROOT / "rv32_peripherals.sv", ROOT / "change-receipt.json", ROOT / "timer_observer.sv.in", Path(__file__),
                 CPU / "sim/peripherals_tb.sv", BASE / "rtl/rv32_peripherals.sv", BASE / "rtl/rv32_fifo.sv", BASE / "rtl/rv32_uart.sv"]
    before = {str(path): digest(path) for path in originals}
    tests = unittest.main(verbosity=2, exit=False)
    after = {str(path): digest(path) for path in originals}
    stable = before == after
    report = {"schema": 1, "scope": "full peripheral simulation, timer carry boundaries and compiled timer fault checks; not PDS or score qualification",
              "passed": tests.result.wasSuccessful() and stable, "tests_run": tests.result.testsRun,
              "sources": before, "sources_unchanged": stable,
              "outputs": {path.relative_to(OUTPUT).as_posix(): digest(path) for path in OUTPUT.rglob("*") if path.is_file()}}
    (OUTPUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Functional evidence: " + str(OUTPUT), flush=True)
    raise SystemExit(0 if report["passed"] else 1)
