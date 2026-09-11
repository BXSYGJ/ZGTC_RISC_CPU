import hashlib
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
ROOT = EXPERIMENT.parents[1]
BASELINE = ROOT / "build/regfile-valid-fanout-stage"
SPEC = json.loads((EXPERIMENT / "source-delta.json").read_text(encoding="utf-8"))
RUNS = []


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def unique(pattern, source):
    matches = re.findall(pattern, source, re.S)
    if len(matches) != 1:
        raise ValueError("Actual source extraction must be unique: " + pattern)
    return matches[0]


def wrapper(source, name):
    functions = [unique(r"    function automatic " + signature + r".*?    endfunction", source)
                 for signature in (r"parallel_less\(", r"\[2:0\] operand_relation\(")]
    selection = unique(r"    always @\* begin\n        compare_next_a=ex_operand_a;.*?    end\n", source)
    refresh = unique(r"            if\(ex_valid\) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b;[^\n]* end", source)
    capture = unique(r"            if\(id_fire\) begin\n                id_valid<=0;(.*?)\n            end", source)
    capture_updates = re.findall(r"(?:ex_operand_[ab]|raw_pair_relation)<=[^;]+;", capture)
    if len(capture_updates) not in (2, 3):
        raise ValueError("Unexpected ID operand capture")
    reset = []
    for signal in ("ex_operand_a", "ex_operand_b", "raw_pair_relation"):
        values = re.findall(r"\b" + signal + r"<=([^;]+);", source)
        reset.append(signal + "<=" + values[0] + ";")
    shared = re.findall(r"            if\([^\n]+\) raw_pair_relation<=operand_relation\([^;]+;", source)
    if len(shared) > 1:
        raise ValueError("Multiple shared updates")
    if source.index(refresh) > source.index(capture):
        raise ValueError("ID priority changed")
    if shared and source.index(shared[0]) < source.index(capture):
        raise ValueError("Shared update moved before capture")
    expected_updates = 2 if shared else 3
    if len(re.findall(r"\braw_pair_relation<=", source)) != expected_updates:
        raise ValueError("Unexpected relation update inventory")
    return "\n".join([
        "module " + name + "(input wire clk,rst_n,ex_valid,id_fire,mem_fire,mem_fault,",
        "input wire [31:0] forwarded_a,forwarded_b,id_operand_a,id_operand_b,wb_data,mem_value,",
        "output reg [31:0] ex_operand_a,ex_operand_b, output reg [2:0] raw_pair_relation);",
        "reg [31:0] compare_next_a,compare_next_b,compare_next_wb;",
        *functions, selection,
        "always @(posedge clk or negedge rst_n) begin",
        "if(!rst_n) begin", *reset, "end else begin", refresh,
        "if(id_fire) begin", *capture_updates, "end", *shared, "end end endmodule",
    ])


class SharedRelationTests(unittest.TestCase):
    def test_exact_source_delta(self):
        self.assertEqual(digest(BASELINE / "rtl/rv32_core.sv"), SPEC["baseline_core_sha256"])
        for directory in ("rtl", "fpga", "constraints"):
            baseline_files = {item.relative_to(BASELINE / directory) for item in (BASELINE / directory).rglob("*") if item.is_file()}
            actual_files = {item.relative_to(EXPERIMENT / directory) for item in (EXPERIMENT / directory).rglob("*") if item.is_file()}
            self.assertEqual(baseline_files, actual_files)
            for relative in baseline_files:
                if directory == "rtl" and relative.name == "rv32_core.sv":
                    continue
                self.assertEqual((BASELINE / directory / relative).read_bytes(), (EXPERIMENT / directory / relative).read_bytes())
        original = (BASELINE / "rtl/rv32_core.sv").read_text(encoding="utf-8-sig")
        for before, after in SPEC["edits"]:
            self.assertEqual(original.count(before), 1)
            original = original.replace(before, after)
        self.assertEqual(original, (EXPERIMENT / "rtl/rv32_core.sv").read_text(encoding="utf-8-sig"))

    def simulate(self, candidate, label):
        baseline = (BASELINE / "rtl/rv32_core.sv").read_text(encoding="utf-8-sig")
        with tempfile.TemporaryDirectory(prefix="shared-relation-") as temporary:
            work = Path(temporary)
            design = work / "design.sv"
            design.write_text(wrapper(baseline, "reference") + "\n" + wrapper(candidate, "candidate"), encoding="utf-8")
            binary = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "shared_relation_tb", "-o", str(binary), str(design), str(EXPERIMENT / "shared_relation_tb.sv")], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(binary)], capture_output=True, text=True, timeout=60)
            RUNS.append({"label": label, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            print(label + ": " + result.stdout.strip(), flush=True)
            return result

    def test_cycle_equivalence(self):
        result = self.simulate((EXPERIMENT / "rtl/rv32_core.sv").read_text(encoding="utf-8-sig"), "positive")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS shared_relation cycles=32768", result.stdout)

    def test_runtime_mutants(self):
        source = (EXPERIMENT / "rtl/rv32_core.sv").read_text(encoding="utf-8-sig")
        mutations = (
            ("wrong_capture_guard", "if(ex_valid || id_fire) raw_pair_relation", "if(ex_valid && id_fire) raw_pair_relation"),
            ("missing_ex_refresh", "if(ex_valid || id_fire) raw_pair_relation", "if(id_fire) raw_pair_relation"),
            ("wrong_id_priority", "if(id_fire) begin compare_next_a=id_operand_a; compare_next_b=id_operand_b; end", "if(id_fire) begin compare_next_a=forwarded_a; compare_next_b=forwarded_b; end"),
            ("reversed_operands", "operand_relation(compare_next_a,compare_next_b)", "operand_relation(compare_next_b,compare_next_a)"),
            ("wrong_reset", "raw_pair_relation<=3'b100;", "raw_pair_relation<=3'b000;"),
            ("wrong_sign", "? operand_left[31] : unsigned_less", "? operand_right[31] : unsigned_less"),
        )
        for label, before, after in mutations:
            with self.subTest(label=label):
                self.assertEqual(source.count(before), 1)
                result = self.simulate(source.replace(before, after), label)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("RELATION_MISMATCH", result.stdout)


if __name__ == "__main__":
    outcome = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SharedRelationTests))
    build = EXPERIMENT / "build"
    build.mkdir(exist_ok=True)
    receipt = {"simulation_passed": outcome.wasSuccessful(), "scope": "source-extracted raw relation update; not full CPU or CoreMark", "runs": RUNS,
               "sha256": {name: digest(EXPERIMENT / name) for name in ("rtl/rv32_core.sv", "test_shared_relation.py", "shared_relation_tb.sv", "source-delta.json")},
               "hardware_validated": False}
    (build / "relation-regression.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(not outcome.wasSuccessful())
