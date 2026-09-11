import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CommitGateTests(unittest.TestCase):
    def simulate(self, mutation=None):
        source = (ROOT / "rv32_core.sv").read_text()
        start = source.index("    wire stack_destination_link=")
        stop = source.index("    rv32_btb #(", start)
        declarations = source[start:stop]
        if mutation:
            before, after = mutation
            self.assertEqual(declarations.count(before), 1)
            declarations = declarations.replace(before, after)
        pushes = re.findall(r"\.stack_push\(([^()]+)\)", source)
        pops = re.findall(r"\.stack_pop\(([^()]+)\)", source)
        self.assertEqual(len(pushes), 1)
        self.assertEqual(len(pops), 1)
        rows = []
        for destination in range(32):
            for operand in range(32):
                for opcode, function in ((111, 0), (103, 0), (103, 1), (19, 0)):
                    instruction = opcode | destination << 7 | operand << 15 | function << 12
                    call = destination in (1, 5) and (opcode == 111 or (opcode == 103 and function == 0))
                    returns = opcode == 103 and function == 0 and operand in (1, 5) and (destination not in (1, 5) or destination != operand)
                    for flags in range(8):
                        fire, fault, branch = flags & 1, (flags >> 1) & 1, (flags >> 2) & 1
                        commit = fire and not fault and branch
                        rows.append(f"{instruction:x} {fire:x} {fault:x} {branch:x} {int(commit and call):x} {int(commit and returns):x}")
        with tempfile.TemporaryDirectory(prefix="return-stack-gate-") as temporary:
            work = Path(temporary)
            data = work / "vectors.txt"
            data.write_text("\n".join(rows) + "\n")
            testbench = work / "gate.sv"
            lines = ["module gate;", "reg [31:0] mem_instruction;", "reg mem_fire,mem_fault,mem_branch;",
                     declarations, "wire actual_push=" + pushes[0] + ";", "wire actual_pop=" + pops[0] + ";",
                     "reg expected_push,expected_pop; integer descriptor,fields,checks=0; reg [4095:0] vector_path;",
                     "initial begin",
                     'if (!$value$plusargs("vectors=%s",vector_path)) $fatal(1,"Missing vectors");',
                     'descriptor=$fopen(vector_path,"r"); if (!descriptor) $fatal(1,"Missing file");',
                     "while (!$feof(descriptor)) begin",
                     'fields=$fscanf(descriptor,"%h %h %h %h %h %h\\n",mem_instruction,mem_fire,mem_fault,mem_branch,expected_push,expected_pop);',
                     "if (fields==6) begin #1; checks=checks+1;",
                     'if (actual_push!==expected_push || actual_pop!==expected_pop) $fatal(1,"FAIL commit_gate check=%0d",checks);',
                     'end else if (fields!=-1) $fatal(1,"Malformed vector"); end',
                     '$display("PASS commit_gate checks=%0d",checks); $finish; end endmodule']
            testbench.write_text("\n".join(lines) + "\n")
            executable = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "gate", "-o", str(executable), str(testbench)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["vvp", str(executable), "+vectors=" + str(data)], capture_output=True, text=True, timeout=60)
            output = executed.stdout + executed.stderr
            if mutation:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL commit_gate", output)
            else:
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn(f"PASS commit_gate checks={len(rows)}", output)
            print(output.strip(), flush=True)

    def test_source_extracted_commit_and_hint_logic(self):
        self.simulate()

    def test_four_faulty_commit_or_hint_conditions_rejected(self):
        for mutation in (("mem_fire && !mem_fault && mem_branch", "!mem_fault && mem_branch"),
                         ("mem_fire && !mem_fault && mem_branch", "mem_fire && mem_branch"),
                         ("mem_fire && !mem_fault && mem_branch", "mem_fire && !mem_fault"),
                         ("mem_instruction[19:15]==5'd5", "1'b0")):
            with self.subTest(mutation=mutation):
                self.simulate(mutation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
