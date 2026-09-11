import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CANDIDATE = PROJECT / "experiments/mmio_ready_payload/rv32_memory_system.sv"
REFERENCE = PROJECT / "rtl/rv32_memory_system.sv"


class MmioReadyPayloadTests(unittest.TestCase):
    def simulate(self, fast_read=1, fast_write=1, instruction_bits=8, stalls=5, mutation=None):
        candidate = CANDIDATE.read_text(encoding="utf-8")
        if mutation is not None:
            before, after = mutation
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        reference = REFERENCE.read_text(encoding="utf-8").replace(
            "module rv32_memory_system #(", "module rv32_memory_system_reference #(")
        bench = (PROJECT / "sim/memory_overlap_tb.sv").read_text(encoding="utf-8")
        widths = {
            "i_req_ready": 1, "i_rsp_valid": 1, "i_rsp_error": 1, "i_rsp_data": 32,
            "d_req_ready": 1, "d_rsp_valid": 1, "d_rsp_error": 1, "d_rsp_data": 32,
            "maintenance_ready": 1, "maintenance_error": 1,
            "mmio_req_valid": 1, "mmio_req_write": 1, "mmio_rsp_ready": 1,
            "mmio_req_address": 32, "mmio_req_data": 32, "mmio_req_strobe": 4,
            "i_hit_count": 32, "i_miss_count": 32, "d_hit_count": 32,
            "d_miss_count": 32, "d_writeback_count": 32,
        }
        inputs = ("clk rst_n i_req_valid i_rsp_ready i_req_address d_req_valid d_req_write "
                  "d_rsp_ready maintenance_valid d_req_address d_req_data d_req_strobe "
                  "mmio_req_ready mmio_rsp_valid mmio_rsp_error mmio_rsp_data").split()
        declarations = [f"wire [{width - 1}:0] reference_{name};" for name, width in widths.items()]
        connections = [f".{name}({name})" for name in inputs]
        connections += [f".{name}(reference_{name})" for name in widths]
        declarations += [
            "rv32_memory_system_reference #(.DATA_OVERLAP(DATA_OVERLAP),"
            ".FAST_DCACHE_WRITE(FAST_DCACHE_WRITE),.FAST_DCACHE_READ(FAST_DCACHE_READ),"
            ".ICACHE_SET_BITS(ICACHE_SET_BITS),.CACHE_SET_BITS(1)) reference_memory("
            + ",".join(connections) + ");",
            "integer equivalence_cycles=0;",
            "always @(negedge clk) if(rst_n) begin",
            "    equivalence_cycles=equivalence_cycles+1;",
        ]
        payload = {"i_rsp_data", "d_rsp_data", "d_rsp_error", "i_rsp_error",
                   "mmio_req_address", "mmio_req_data", "mmio_req_write", "mmio_req_strobe"}
        for name in widths:
            if name not in payload:
                declarations.append(f'    check({name}===reference_{name},"miter {name}");')
        for valid, names in (("i_rsp_valid", ("i_rsp_data", "i_rsp_error")),
                             ("d_rsp_valid", ("d_rsp_data", "d_rsp_error")),
                             ("mmio_req_valid", ("mmio_req_address", "mmio_req_data", "mmio_req_write", "mmio_req_strobe"))):
            for name in names:
                declarations.append(f'    if({valid}) check({name}===reference_{name},"miter valid {name}");')
        declarations += ["end"]
        bench = bench.replace("    task automatic check", "\n".join(declarations) + "\n    task automatic check")
        initialization = "memory_system.ram.memory[word_index]=32'h10000000+32'(word_index);"
        self.assertEqual(bench.count(initialization), 1)
        bench = bench.replace(initialization, "begin " + initialization + " reference_memory.ram.memory[word_index]=32'h10000000+32'(word_index); end")
        bench = bench.replace('        $display("PASS %s', '        check(equivalence_cycles>40,"miter exercised cycles");\n        $display("PASS %s')
        with tempfile.TemporaryDirectory(prefix="mmio-payload-") as directory:
            work = Path(directory)
            candidate_file = work / "candidate.sv"
            candidate_file.write_text(candidate, encoding="utf-8")
            reference_file = work / "reference.sv"
            reference_file.write_text(reference, encoding="utf-8")
            bench_file = work / "bench.sv"
            bench_file.write_text(bench, encoding="utf-8")
            sources = [PROJECT / "experiments/cache_synchronous_writable/rv32_cache.sv"]
            sources += [PROJECT / "rtl" / name for name in (
                "rv32_uncached.sv", "rv32_burst_arbiter.sv", "rv32_burst_ram.sv")]
            output = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "memory_overlap_tb",
                       f"-Pmemory_overlap_tb.FAST_DCACHE_READ={fast_read}",
                       f"-Pmemory_overlap_tb.FAST_DCACHE_WRITE={fast_write}",
                       f"-Pmemory_overlap_tb.ICACHE_SET_BITS={instruction_bits}",
                       f"-Pmemory_overlap_tb.MMIO_STALL_CYCLES={stalls}",
                       "-o", str(output), str(candidate_file), str(reference_file),
                       *map(str, sources), str(bench_file)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=45)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=45)

    def test_cycle_equivalence_under_handover_backpressure_and_reset(self):
        for fast_read, fast_write, bits, stalls in itertools.product((0, 1), (0, 1), (1, 8, 9), (0, 5)):
            with self.subTest(fast_read=fast_read, fast_write=fast_write, bits=bits, stalls=stalls):
                result = self.simulate(fast_read, fast_write, bits, stalls)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS memory_overlap checks=", result.stdout)
                self.assertIn("handovers=4", result.stdout)

    def test_compiled_payload_and_control_faults_rejected(self):
        mutations = (
            ("if(!mmio_request_pending) begin", "if(1'b1) begin"),
            ("if(!mmio_request_pending) begin", "if(mmio_request_pending) begin"),
            ("if(d_req_valid && d_req_ready && request_mmio) mmio_request_pending<=1;",
             "if(request_mmio) mmio_request_pending<=1;"),
            ("mmio_request_strobe<=d_req_strobe;", "mmio_request_strobe<=4'b0;"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL memory_overlap", result.stdout)
                self.assertNotIn("watchdog", result.stdout.lower())
                self.assertNotIn("PASS memory_overlap", result.stdout)


if __name__ == "__main__":
    unittest.main()
