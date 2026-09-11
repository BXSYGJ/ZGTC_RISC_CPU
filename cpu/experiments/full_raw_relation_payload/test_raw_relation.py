import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_return_stack_link"


class RawRelationTests(unittest.TestCase):
    def simulate(self, variant="positive"):
        candidate = (ROOT / "rv32_core.sv").read_text()
        original = (PARENT / "rv32_core.sv").read_text()
        before = "            if(ex_valid) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b; raw_pair_relation<=operand_relation(forwarded_a,forwarded_b); end"
        after = "            raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);\n            if(ex_valid) begin ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b; end"
        self.assertEqual(original.count(before), 1)
        self.assertEqual(candidate, original.replace(before, after))
        functions = re.findall(r"    function automatic.*?endfunction", candidate, re.S)
        functions = "\n".join(text for text in functions if "parallel_less(" in text or "operand_relation(" in text)
        self.assertEqual(functions.count("endfunction"), 2)
        reference_update = before.replace("ex_operand_a<=forwarded_a; ex_operand_b<=forwarded_b; ", "").replace("raw_pair_relation", "reference_relation")
        id_update = "raw_pair_relation<=operand_relation(id_operand_a,id_operand_b);"
        self.assertEqual(candidate.count(id_update), 1)
        candidate_id = id_update
        trailing = ""
        if variant == "drop_id_capture":
            candidate_id = "raw_pair_relation<=raw_pair_relation;"
        elif variant == "freeze_forwarded_capture":
            after = after.replace("raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);", "raw_pair_relation<=raw_pair_relation;")
        elif variant == "late_refresh_overrides_id":
            trailing = "raw_pair_relation<=operand_relation(forwarded_a,forwarded_b);"
        template = r"""
module raw_relation_tb;
    reg clk=0,rst_n=0,ex_valid=0,ex_fire,id_fire,flush;
    reg [31:0] ex_operand_a=0,ex_operand_b=0,forwarded_a,forwarded_b,id_operand_a,id_operand_b;
    reg [2:0] raw_pair_relation=3'b100,reference_relation=3'b100;
    reg [31:0] random_state=32'hbade1234;
    integer step,live_checks=0,invalid_changes=0,held_checks=0,flushes=0;
__FUNCTIONS__
    always @(posedge clk) begin
        if(!rst_n) begin
            ex_valid<=0; ex_operand_a<=0; ex_operand_b<=0;
            raw_pair_relation<=3'b100; reference_relation<=3'b100;
        end else begin
__REFERENCE__
__CANDIDATE__
            if(ex_fire) ex_valid<=0;
            if(id_fire) begin
                ex_valid<=1;
                ex_operand_a<=id_operand_a; ex_operand_b<=id_operand_b;
                reference_relation<=operand_relation(id_operand_a,id_operand_b);
                __ID__
            end
__TRAILING__
            if(flush) ex_valid<=0;
        end
    end
    initial begin
        for(step=0;step<10000;step=step+1) begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            rst_n=(step%127)!=0;
            ex_fire=ex_valid && random_state[0];
            id_fire=(!ex_valid || ex_fire) && random_state[2];
            flush=random_state[5:0]==6'h2a;
            forwarded_a=random_state; forwarded_b={random_state[15:0],~random_state[31:16]};
            id_operand_a=~random_state; id_operand_b=random_state^32'h80000000;
            if(step%17==0) forwarded_a[7:0]=8'hxx;
            if(step%19==0) id_operand_b[31]=1'bx;
            if(step%23==0) forwarded_b[15:8]=8'hzz;
            if(ex_valid && !ex_fire && !id_fire) held_checks=held_checks+1;
            if(flush) flushes=flushes+1;
            #5; clk=1; #1;
            if(rst_n && ex_valid) begin
                live_checks=live_checks+1;
                if(raw_pair_relation!==reference_relation || raw_pair_relation!==operand_relation(ex_operand_a,ex_operand_b))
                    $fatal(1,"FAIL raw_relation_payload live step=%0d candidate=%b reference=%b",step,raw_pair_relation,reference_relation);
            end
            if(rst_n && !ex_valid && raw_pair_relation!==reference_relation) invalid_changes=invalid_changes+1;
            #4; clk=0;
        end
        if(live_checks<1000 || held_checks<1000 || invalid_changes<100 || flushes<50)
            $fatal(1,"FAIL raw_relation_payload insufficient coverage");
        $display("PASS raw_relation_payload cycles=10000 live=%0d held=%0d invalid_changes=%0d flushes=%0d",live_checks,held_checks,invalid_changes,flushes);
        $finish;
    end
endmodule
"""
        for anchor, text in (("__FUNCTIONS__", functions), ("__REFERENCE__", reference_update), ("__CANDIDATE__", after), ("__ID__", candidate_id), ("__TRAILING__", trailing)):
            self.assertEqual(template.count(anchor), 1)
            template = template.replace(anchor, text)
        with tempfile.TemporaryDirectory(prefix="raw-relation-payload-") as temporary:
            work = Path(temporary)
            bench = work / "test.sv"
            bench.write_text(template)
            executable = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "raw_relation_tb", "-o", str(executable), str(bench)], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["vvp", str(executable)], capture_output=True, text=True, timeout=60)
            output = executed.stdout + executed.stderr
            if variant == "positive":
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn("PASS raw_relation_payload", output)
            else:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL raw_relation_payload live", output)
            print(output.strip(), flush=True)

    def test_source_extracted_live_equivalence(self):
        self.simulate()

    def test_three_compiled_capture_faults_rejected(self):
        for variant in ("drop_id_capture", "freeze_forwarded_capture", "late_refresh_overrides_id"):
            with self.subTest(variant=variant):
                self.simulate(variant)


if __name__ == "__main__":
    unittest.main(verbosity=2)
