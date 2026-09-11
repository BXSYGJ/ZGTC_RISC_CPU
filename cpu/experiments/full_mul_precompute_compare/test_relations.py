import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_mul_precompute"


def extract(source, name):
    begin = source.index("    always @* begin\n        compare_next_a=ex_operand_a;")
    end = source.index("    genvar compare_pair,compare_byte;", begin)
    body = source[begin:end]
    header = """module NAME(
        input wire clk,rst_n,ex_valid,id_fire,mem_fire,mem_fault,
        input wire [31:0] ex_operand_a,ex_operand_b,forwarded_a,forwarded_b,
        input wire [31:0] id_operand_a,id_operand_b,wb_data,mem_value,
        output wire [15:0] result);
    reg [31:0] compare_next_a,compare_next_b,compare_next_wb;
    reg [3:0] wb_a_byte_equal,wb_a_byte_less,wb_b_byte_equal,wb_b_byte_less;
    integer wb_compare_byte;
    assign result={wb_a_byte_equal,wb_a_byte_less,wb_b_byte_equal,wb_b_byte_less};
""".replace("NAME", name)
    return header + body + "endmodule\n"


class RelationTests(unittest.TestCase):
    def simulate(self, mutation=None):
        original = (PARENT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        candidate = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        reference_wrapper = extract(original, "baseline")
        candidate_wrapper = extract(candidate, "candidate")
        if mutation:
            before, after = mutation
            self.assertEqual(candidate_wrapper.count(before), 1)
            candidate_wrapper = candidate_wrapper.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="wb-compare-select-") as directory:
            work = Path(directory)
            wrappers = work / "wrappers.sv"
            wrappers.write_text(reference_wrapper + candidate_wrapper, encoding="utf-8")
            image = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "relation_tb", "-o", str(image), str(wrappers), str(ROOT / "relation_tb.sv")], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=60)

    def test_four_state_equivalence(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS WB relation checks=32768", result.stdout)
        print(result.stdout.strip())

    def test_runtime_mutations_rejected(self):
        mutations = [("if(id_fire)", "if(!id_fire)"),
                     ("id_operand_a[wb_relation_byte*8+:8]<compare_next_wb", "id_operand_a[wb_relation_byte*8+:8]>compare_next_wb"),
                     ("if(mem_fire && !mem_fault)", "if(mem_fire)"),
                     ("wb_a_byte_equal<=4'b1111", "wb_a_byte_equal<=4'b0000")]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL relation", result.stdout)

    def test_exact_delta(self):
        receipt = json.loads((ROOT / "source-delta.json").read_text())
        original = (PARENT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        for before, after in receipt["edits"]:
            self.assertEqual(original.count(before), 1)
            original = original.replace(before, after)
        self.assertEqual(original, (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8"))
        for directory in ("rtl", "fpga", "constraints"):
            for filename in (PARENT / directory).iterdir():
                if filename.is_file() and filename.name != "rv32_core.sv":
                    self.assertEqual(filename.read_bytes(), (ROOT / directory / filename.name).read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)

