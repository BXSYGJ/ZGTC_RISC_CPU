import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
PARENT = ROOT.parent / "full_mul_prefetch_valid1"


class DecodePayloadTests(unittest.TestCase):
    def simulate(self, bench, overlap, predictor, mutation=None):
        source = (ROOT / "rv32_core.sv").read_text(encoding="utf-8")
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="prediction-payload-") as temporary:
            work = Path(temporary)
            candidate = work / "rv32_core.sv"
            candidate.write_text(source, encoding="utf-8")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", bench,
                       f"-P{bench}.FETCH_OVERLAP={overlap}", f"-P{bench}.PREDICTOR={predictor}",
                       "-o", str(image), str(candidate)]
            if bench == "decode_payload_tb":
                original = (PARENT / "rv32_core.sv").read_text(encoding="utf-8")
                self.assertEqual(original.count("module rv32_core #("), 1)
                reference = work / "rv32_core_reference.sv"
                reference.write_text(original.replace("module rv32_core #(", "module rv32_core_reference #("), encoding="utf-8")
                command.append(str(reference))
            command.extend(str(ROOT / "rv32_btb.sv" if name == "rv32_btb" else BASE / "rtl" / (name + ".sv")) for name in
                           ("rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv"))
            command.append(str(ROOT / (bench + ".sv")))
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            self.assertNotIn("only be evaluated once", compiled.stderr)
            for diagnostic in compiled.stderr.splitlines():
                if diagnostic.strip():
                    self.assertIn("warning: Attributes are not supported on net declaration assignments and will be discarded.", diagnostic)
            self.assertNotIn("parameter RESET_PC not found", compiled.stderr)
            executed = subprocess.run(["vvp", str(image)], capture_output=True, text=True, timeout=60)
            output = executed.stdout + executed.stderr
            marker = "decode_payload" if bench == "decode_payload_tb" else "redirect_prime"
            if mutation:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL " + marker, output)
            else:
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn("PASS " + marker, output)
            print(output.strip(), flush=True)

    def test_exact_source_delta(self):
        record = json.loads((ROOT / "change-receipt.json").read_text(encoding="utf-8"))
        original = (ROOT.parent / record["parent"] / "rv32_core.sv").read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest().upper(), record["parent_core_sha256"])
        expected = original.decode("utf-8")
        for before, after in record["substitutions"]:
            self.assertEqual(expected.count(before), 1)
            expected = expected.replace(before, after)
        actual = (ROOT / "rv32_core.sv").read_bytes()
        self.assertEqual(actual, expected.encode("utf-8"))
        self.assertEqual(hashlib.sha256(actual).hexdigest().upper(), record["candidate_core_sha256"])

    def test_randomized_equivalence(self):
        for overlap in (0, 1):
            for predictor in (0, 1):
                with self.subTest(overlap=overlap, predictor=predictor):
                    self.simulate("decode_payload_tb", overlap, predictor)

    def test_capture_faults_rejected(self):
        mutations = (
            ("id_payload_load=!id_valid ||", "id_payload_load=1'b0 ||"),
            ("!id_valid || !ex_valid || ex_fire;", "!id_valid || 1'b0 || ex_fire;"),
            ("!id_valid || !ex_valid || ex_fire;", "!id_valid || !ex_valid || 1'b0;"),
            ("if(id_payload_load)", "if(1'b1)"),
            ("id_pc<=if_pc; id_instruction<=if_instruction;", "id_pc<=if_pc+32'd4; id_instruction<=if_instruction;"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate("decode_payload_tb", 1, 1, mutation)

    def test_directed_redirect_cases(self):
        for overlap in (0, 1):
            for predictor in (0, 1):
                with self.subTest(overlap=overlap, predictor=predictor):
                    self.simulate("redirect_prime_tb", overlap, predictor)


if __name__ == "__main__":
    unittest.main(verbosity=2)
