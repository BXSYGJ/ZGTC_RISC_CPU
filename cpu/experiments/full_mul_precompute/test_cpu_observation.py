import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
ISA = ROOT / "build/isa/20260910-182943-c2f787ee"
OBSERVER = """
    integer precomputed_checks=0,fallback_checks=0,expired_checks=0;
    reg [31:0] multiply_expected;
    reg observer_reported=0;
    always @(posedge clk) if(rst_n) begin
        if(core.ex_valid && core.ex_muldiv && core.ex_instruction[14:12]==0 &&
           core.ex_fire && !core.execute_common_exception && !core.execute_local_exception) begin
            multiply_expected=core.forwarded_a*core.forwarded_b;
            if(core.execute_result!==multiply_expected)
                $fatal(1,"FAIL multiply operand observation pc=%08x",core.ex_pc);
            if(core.mul_precomputed) precomputed_checks=precomputed_checks+1;
            else fallback_checks=fallback_checks+1;
        end
        if(core.mul_precomputed && !core.ex_fire) expired_checks=expired_checks+1;
        if(passed && success_wait>=19 && !observer_reported) begin
            observer_reported=1;
            $display("MUL_OBSERVER precomputed=%0d fallback=%0d expired=%0d",precomputed_checks,fallback_checks,expired_checks);
        end
    end
"""


class CpuObservationTests(unittest.TestCase):
    def test_actual_cpu_mul_results(self):
        original = (ROOT / "sim/isa_tb.sv").read_text(encoding="utf-8")
        self.assertEqual(original.count("endmodule"), 1)
        bench = original.replace("endmodule", OBSERVER + "endmodule")
        firmware = ISA / "mul.hex"
        report = json.loads((ISA / "results.json").read_text())
        expected_hash = next(result["hex_sha256"] for result in report["results"] if result["name"] == "mul")
        self.assertEqual(hashlib.sha256(firmware.read_bytes()).hexdigest(), expected_hash)
        totals = [0, 0, 0]
        with tempfile.TemporaryDirectory(prefix="cpu-mul-observer-") as temporary:
            work = Path(temporary)
            testbench = work / "isa_tb.sv"
            testbench.write_text(bench, encoding="utf-8")
            for predictor, cached, sets in ((0, 0, 4), (1, 0, 4), (0, 1, 1), (1, 1, 4)):
                config = f"p{predictor}_c{cached}_s{sets}"
                parameters = {"ENABLE_M": 1, "PREDICTOR": predictor, "ENABLE_CACHE": cached, "CACHE_SETS": sets,
                              "LOAD_USE_BUBBLE": 1, "FAST_ICACHE_HIT": 1, "FAST_DCACHE_READ": 1,
                              "FAST_DCACHE_WRITE": 1, "FETCH_OVERLAP": 1, "DATA_OVERLAP": 1,
                              "EARLY_D_REQUEST": 1, "BTB_INDEX_BITS": 8, "ICACHE_SET_BITS": 9}
                image = work / (config + ".vvp")
                command = ["iverilog", "-g2012", "-s", "isa_tb", "-o", str(image)]
                command += [f"-Pisa_tb.{key}={value}" for key, value in parameters.items()]
                command += [str(source) for source in sorted((ROOT / "rtl").glob("*.sv"))] + [str(testbench)]
                compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
                self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                trace = work / (config + ".trace")
                memory = work / (config + ".memory")
                result = subprocess.run(["vvp", str(image), f"+firmware={firmware.as_posix()}", "+name=mul", f"+trace={trace.as_posix()}", f"+memory_out={memory.as_posix()}"], capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS", result.stdout)
                matches = re.findall(r"MUL_OBSERVER precomputed=(\d+) fallback=(\d+) expired=(\d+)", result.stdout)
                self.assertEqual(len(matches), 1, result.stdout)
                values = [int(value) for value in matches[0]]
                totals = [total + value for total, value in zip(totals, values)]
                self.assertEqual(trace.read_text().splitlines(), (ISA / ("mul_" + config + ".trace")).read_text().splitlines())
                self.assertEqual(memory.read_text().splitlines(), (ISA / ("mul_" + config + ".memory")).read_text().splitlines())
                print(config, values, "identical retirement trace and memory lines; OS newline normalization only")
        self.assertGreater(totals[0], 0)
        self.assertGreater(totals[1], 0)
        print("Observed totals precomputed/fallback/expired:", totals)


if __name__ == "__main__":
    unittest.main(verbosity=2)
