from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class PendingInvariantTests(unittest.TestCase):
    def test_actual_rtl_one_step_induction(self):
        original = (ROOT / "redirect_prime_tb.sv").read_text(encoding="utf-8")
        start = original.index("    initial begin")
        prefix = original[:start].replace("    integer checks=0,cases=0;", "    integer checks=0,cases=0;\n    reg accept_space=0;")
        self.assertIn("reg accept_space=0;", prefix)
        body = "\n".join([
            "    initial begin",
            "        force dut.frontend_flush=flush;",
            "        force dut.frontend_barrier=barrier;",
            "        force dut.redirect_pc=redirect;",
            "        force dut.fetch_accept_space=accept_space;",
            "        for(integer state=0;state<16;state=state+1) begin",
            "            if(!state[3] || state==9) begin",
            "                for(integer control=0;control<32;control=control+1) begin",
            "                    reset_core();",
            "                    dut.fetch_active=state[0]; dut.fetch_sent=state[1];",
            "                    dut.fetch_discard=state[2]; dut.fetch_redirect_pending=state[3];",
            "                    request_ready=control[0]; response_valid=control[1];",
            "                    accept_space=control[2]; flush=control[3]; barrier=control[4];",
            "                    redirect=32'h100; #1;",
            "                    if(dut.fetch_redirect_pending) check(dut.i_req_valid,\"pending implies request valid\");",
            "                    check(dut.redirect_prediction_commit === (dut.fetch_redirect_pending && dut.i_req_valid && request_ready && !flush && !barrier),\"predicate equivalence\");",
            "                    step();",
            "                end",
            "            end",
            "        end",
            "        check(cases==288,\"all invariant states and control combinations covered\");",
            "        $display(\"PASS induction transitions=%0d checks=%0d overlap=%0d\",cases,checks,FETCH_OVERLAP);",
            "        $finish;",
            "    end",
            "endmodule", ""])
        with tempfile.TemporaryDirectory(prefix="fetch-pending-induction-") as directory:
            work = Path(directory)
            bench = work / "induction.sv"
            bench.write_text(prefix + body, encoding="utf-8")
            sources = [ROOT / "rtl" / name for name in
                       ("rv32_core.sv", "rv32_machine.sv", "rv32_decode.sv", "rv32_alu.sv", "rv32_btb.sv", "rv32_muldiv.sv")]
            for overlap in (0, 1):
                image = work / "test.vvp"
                compiled = subprocess.run(["iverilog", "-g2012", "-s", "redirect_prime_tb",
                                           f"-Predirect_prime_tb.FETCH_OVERLAP={overlap}", "-o", str(image),
                                           *map(str, sources), str(bench)], capture_output=True, text=True, timeout=60)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                result = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS induction transitions=288", result.stdout)
                print(result.stdout.strip(), flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

