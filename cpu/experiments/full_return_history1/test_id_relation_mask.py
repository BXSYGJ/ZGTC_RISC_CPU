from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_decode_payload1"


def extract_function(source, name):
    pattern = r"    function automatic(?: \[2:0\])? " + re.escape(name) + r"\(.*?    endfunction"
    matches = re.findall(pattern, source, re.S)
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous function: " + name)
    return matches[0]


class RelationMaskTests(unittest.TestCase):
    def simulate(self, mutation=None):
        source = (ROOT / "rv32_core.sv").read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        functions = "\n".join(extract_function(source, name) for name in
                              ("parallel_less", "operand_relation", "masked_operand_relation"))
        start = source.index("    (* syn_maxfan=16 *) wire id_register_a_valid")
        end = source.index("    always @* begin", start)
        declarations = source[start:end]
        parent = (PARENT / "rv32_core.sv").read_text()
        for name in ("id_operand_a", "id_operand_b"):
            pattern = r"    wire \[31:0\] " + name + r"=.*?;"
            self.assertEqual(re.findall(pattern, declarations), re.findall(pattern, parent))
        bench = (ROOT / "id_relation_mask_tb.sv.in").read_text()
        bench = bench.replace("    __FUNCTIONS__", functions).replace("    __DECLARATIONS__", declarations)
        with tempfile.TemporaryDirectory(prefix="id-relation-mask-") as temporary:
            work = Path(temporary)
            testbench = work / "test.sv"
            image = work / "test.vvp"
            testbench.write_text(bench)
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "id_relation_mask_tb", "-o", str(image), str(testbench)],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            diagnostics = compiled.stderr.splitlines()
            self.assertEqual(len(diagnostics), 2, compiled.stderr)
            for diagnostic in diagnostics:
                self.assertRegex(diagnostic, r"^.*test\.sv:\d+: warning: Attributes are not supported on net declaration assignments and will be discarded\.$")
            executed = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=60)
            output = executed.stdout + executed.stderr
            if mutation:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL mask", output)
            else:
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn("PASS mask checks=32768", output)
            print(output.strip(), flush=True)

    def test_relation_equivalence_with_masked_unknowns(self):
        self.simulate()

    def test_compiled_faults_rejected(self):
        mutations = (
            (" : 3'b100);", " : 3'b000);"),
            ("{operand_left==0,1'b0,operand_left[31]}", "{operand_left==0,1'b1,operand_left[31]}"),
            ("!operand_right[31] && operand_right!=0", "operand_right[31] && operand_right!=0"),
            ("wire id_relation_a_valid=id_register_a_valid || (trace_write && wb_rd==id_rs1);", "wire id_relation_a_valid=id_register_a_valid;"),
            ("wire id_relation_b_valid=id_register_b_valid || (trace_write && wb_rd==id_rs2);", "wire id_relation_b_valid=id_register_b_valid;"),
            ("wire [31:0] mul_id_operand_b=(trace_write && wb_rd==id_rs2) ? wb_data : registers[id_rs2];", "wire [31:0] mul_id_operand_b=(trace_write && wb_rd==id_rs1) ? wb_data : registers[id_rs2];"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate(mutation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
