from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class RedirectPrimeTests(unittest.TestCase):
    def simulate(self, overlap=1, predictor=1, mutant=None):
        source = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        if mutant:
            before, after = mutant
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="redirect-prime-") as directory:
            work = Path(directory)
            core = work / "rv32_core.sv"
            core.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "redirect_prime_tb",
                       f"-Predirect_prime_tb.FETCH_OVERLAP={overlap}",
                       f"-Predirect_prime_tb.PREDICTOR={predictor}", "-o", str(image), str(core)]
            command += [str(ROOT / "rtl" / name) for name in
                        ("rv32_machine.sv", "rv32_decode.sv", "rv32_alu.sv", "rv32_btb.sv", "rv32_muldiv.sv")]
            command.append(str(ROOT / "redirect_prime_tb.sv"))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=60)
            output = result.stdout + result.stderr
            if mutant:
                self.assertNotEqual(result.returncode, 0, output)
                self.assertIn("FAIL redirect_prime", output)
            else:
                self.assertEqual(result.returncode, 0, output)
                self.assertIn("PASS redirect_prime", output)
            print(output.strip(), flush=True)

    def test_modes(self):
        for overlap in (0, 1):
            for predictor in (0, 1):
                with self.subTest(overlap=overlap, predictor=predictor):
                    self.simulate(overlap, predictor)

    def test_mutants(self):
        mutants = [
            ("fetch_address<=redirect_pc; fetch_redirect_pending<=1;", "fetch_address<=next_pc; fetch_redirect_pending<=1;"),
            ("fetch_address<=redirect_pc; fetch_redirect_pending<=1;", "fetch_address<=redirect_pc; fetch_redirect_pending<=0;"),
            ("if(frontend_flush) begin\n                fetch_redirect_pending<=0;", "if(frontend_flush) begin"),
            ("if(frontend_barrier) begin\n                fetch_redirect_pending<=0;", "if(frontend_barrier) begin"),
            ("if(!frontend_barrier && (!fetch_active || fetch_complete)) begin", "if(!frontend_barrier) begin"),
            ("wire next_pc_write=frontend_flush || next_pc_sequential_write || redirect_prediction_commit;", "wire next_pc_write=frontend_flush || next_pc_sequential_write;"),
        ]
        for index, mutant in enumerate(mutants):
            with self.subTest(mutant=index):
                self.simulate(mutant=mutant)

    def test_source_binding(self):
        receipt = json.loads((ROOT / "source-inputs.json").read_text(encoding="utf-8"))
        changed = []
        for relative, expected in receipt["source_hashes"].items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest().upper()
            self.assertEqual(actual, expected, relative)
            if expected != receipt["parent_hashes"][relative]:
                changed.append(relative)
        self.assertEqual(changed, ["rtl/rv32_core.sv"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

