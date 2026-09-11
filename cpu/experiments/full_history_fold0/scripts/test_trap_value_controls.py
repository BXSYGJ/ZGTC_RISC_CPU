import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class TrapValueControls(unittest.TestCase):
    def simulate(self, replacement=None):
        source = (PROJECT / "rtl" / "rv32_core.sv").read_text(encoding="utf-8")
        if replacement is not None:
            old, new = replacement
            self.assertEqual(source.count(old), 1, "Mutation must match actual RTL exactly once")
            source = source.replace(old, new)
        with tempfile.TemporaryDirectory(prefix="trap-value-") as directory:
            work = Path(directory)
            rtl = work / "rv32_core.sv"
            rtl.write_text(source, encoding="utf-8")
            output = work / "test.vvp"
            dependencies = [PROJECT / "rtl" / (name + ".sv") for name in (
                "rv32_decode", "rv32_alu", "rv32_btb", "rv32_machine", "rv32_muldiv")]
            compiled = subprocess.run([
                "iverilog", "-g2012", "-s", "trap_value_tb", "-o", str(output), str(rtl),
                *map(str, dependencies), str(PROJECT / "sim" / "trap_value_tb.sv"),
            ], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            return subprocess.run(["vvp", str(output)], capture_output=True, text=True, timeout=30)

    def test_registered_exception_contract(self):
        result = self.simulate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS trap_value checks=", result.stdout)

    def test_wrong_exception_sources_are_rejected(self):
        mutations = [
            ("mem_pc[1:0]!=0 ? mem_pc : mem_target", "mem_target"),
            ("mem_pc[1:0]!=0 ? mem_pc : mem_target", "mem_pc"),
            ("1,3: mem_tval=mem_pc;", "1,3: mem_tval=ex_pc;"),
            ("2: mem_tval=mem_instruction;", "2: mem_tval=mem_pc;"),
            ("4,6: mem_tval=mem_address;", "4,6: mem_tval=effective_address;"),
            ("default: mem_tval=0;", "default: mem_tval=mem_address;"),
            ("case(mem_cause)", "case({1'b0,mem_cause[30:0]})"),
            ("mem_exception ? mem_tval : mem_address", "mem_exception ? mem_tval : effective_address"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                result = self.simulate(mutation)
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stdout, r"trap_value (registered exception value under stall|pending access retains full address)")
                self.assertNotIn("timeout", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
