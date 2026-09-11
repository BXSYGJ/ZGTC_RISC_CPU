import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PREVIOUS = ROOT.parent / "full_mul_precompute"


def run(command, timeout=90):
    return subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout)


class PrefetchValidityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        toolchain = json.loads((PREVIOUS / "build/riscv32-toolchain.json").read_text(encoding="utf-8-sig"))
        prefix = toolchain["ToolPrefix"]
        identity = run([prefix + "gcc", "-dumpmachine"])
        if identity.returncode != 0 or identity.stdout.strip() != "riscv32-unknown-elf":
            raise ValueError("Unexpected assembler target")
        for suffix in ("gcc", "objcopy"):
            executable = Path(prefix + suffix)
            print("BOUND " + suffix + "=" + hashlib.sha256(executable.read_bytes()).hexdigest().upper(), flush=True)

    def gate(self, mutation=None):
        source = (ROOT / "rv32_core.sv").read_text()
        start = source.index("    (* syn_maxfan=16 *) wire id_register_a_valid=")
        stop = source.index("    wire [31:0] id_operand_a=", start)
        source = source[start:stop]
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        bench = (ROOT / "prefetch_gate_tb.sv.in").read_text().replace("__DECLARATIONS__", source)
        with tempfile.TemporaryDirectory(prefix="prefetch-gate-") as temporary:
            work = Path(temporary)
            path = work / "gate.sv"
            path.write_text(bench)
            result = run(["iverilog", "-g2012", "-s", "prefetch_gate_tb", "-o", work / "test.vvp", path])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run(["vvp", work / "test.vvp"])
            output = result.stdout + result.stderr
            if mutation:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("FAIL prefetch_gate", output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("PASS prefetch_gate checks=16384 unknown_rejected=1", output)
            print(output.strip(), flush=True)

    def core(self, bench, delay, predictor, mutation=None):
        toolchain = json.loads((PREVIOUS / "build/riscv32-toolchain.json").read_text(encoding="utf-8-sig"))
        prefix = toolchain["ToolPrefix"]
        with tempfile.TemporaryDirectory(prefix="prefetch-core-") as temporary:
            work = Path(temporary)
            for command in ([prefix + "gcc", "-march=rv32im", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-Wl,--no-relax", "-T", BASE / "sim/isa/link.ld", "-o", work / "test.elf", ROOT / (bench + ".S")],
                            [prefix + "objcopy", "-O", "binary", work / "test.elf", work / "test.bin"]):
                result = run(command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            binary = (work / "test.bin").read_bytes()
            self.assertLessEqual(len(binary), 65536)
            binary = binary.ljust(65536, bytes(1))
            firmware = work / "test.hex"
            firmware.write_text("".join(format(int.from_bytes(binary[offset:offset+4], "little"), "08x") + chr(10) for offset in range(0, len(binary), 4)))
            source = (ROOT / "rv32_core.sv").read_text()
            if mutation:
                before, after = mutation
                self.assertEqual(source.count(before), 1)
                source = source.replace(before, after)
            core_path = work / "rv32_core.sv"
            core_path.write_text(source)
            sources = [core_path, ROOT / "rv32_btb.sv"] + [BASE / "rtl" / (name + ".sv") for name in ("rv32_decode", "rv32_machine", "rv32_alu", "rv32_muldiv")]
            top = bench + "_tb"
            result = run(["iverilog", "-g2012", "-s", top, "-P" + top + ".RESPONSE_DELAY=" + str(delay), "-P" + top + ".PREDICTOR=" + str(predictor), "-o", work / "test.vvp", *sources, ROOT / (top + ".sv")])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run(["vvp", work / "test.vvp", "+firmware=" + firmware.as_posix()])
            output = result.stdout + result.stderr
            if mutation:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("FAIL ", output)
                self.assertNotIn("watchdog", output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("PASS " + ("prefetch_valid" if bench == "prefetch_valid" else "stalled precompute"), output)
            print(output.strip(), flush=True)

    def test_gate_truth_table(self):
        self.gate()

    def test_gate_mutants(self):
        for mutation in (("id_rs1!=0 &&", "1'b1 &&"), ("id_rs2!=0 &&", "1'b1 &&"),
                         ("wire mul_id_a_available=id_rs1!=0 && (id_register_a_valid || (trace_write && wb_rd==id_rs1));", "wire mul_id_a_available=id_rs1!=0 && id_register_a_valid;"),
                         ("wire mul_id_b_available=id_rs2!=0 && (id_register_b_valid || (trace_write && wb_rd==id_rs2));", "wire mul_id_b_available=id_rs2!=0 && id_register_b_valid;"),
                         ("? wb_data : registers[id_rs1]", "? registers[id_rs1] : registers[id_rs1]"),
                         ("? wb_data : registers[id_rs2]", "? registers[id_rs2] : registers[id_rs2]")):
            with self.subTest(mutation=mutation):
                self.gate(mutation)

    def test_core_fallbacks(self):
        for delay in (0, 7):
            for predictor in (0, 1):
                with self.subTest(delay=delay, predictor=predictor):
                    self.core("prefetch_valid", delay, predictor)

    def test_core_mutants(self):
        for mutation in (("mul_id_a_available && mul_id_b_available", "mul_id_b_available"),
                         ("mul_id_a_available && mul_id_b_available", "mul_id_a_available"),
                         ("mul_prefetch_operands ? mul_id_operand_a : forwarded_a", "mul_prefetch_operands ? mul_id_operand_a : mul_id_operand_a"),
                         ("mul_prefetch_operands ? mul_id_operand_b : forwarded_b", "mul_prefetch_operands ? mul_id_operand_a : forwarded_b")):
            with self.subTest(mutation=mutation):
                self.core("prefetch_valid", 0, 1, mutation)

    def test_stalls_and_expiry(self):
        for delay in (0, 1, 8, 31):
            for predictor in (0, 1):
                with self.subTest(delay=delay, predictor=predictor):
                    self.core("precompute_stall", delay, predictor)
        self.core("precompute_stall", 31, 1, ("else mul_precomputed<=mul_precompute;", "else if(mul_precompute) mul_precomputed<=1;"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
