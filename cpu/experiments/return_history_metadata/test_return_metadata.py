import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_id_relation_mask1"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest().upper()


class ReturnMetadataTests(unittest.TestCase):
    def test_exact_predictor_delta(self):
        record = json.loads((ROOT / "change-receipt.json").read_text())
        original = (PARENT / "rv32_btb.sv").read_text()
        self.assertEqual(digest(original), record["parent_btb_sha256"])
        self.assertEqual(len(record["substitutions"]), 4)
        for before, after in record["substitutions"]:
            self.assertEqual(original.count(before), 1)
            original = original.replace(before, after)
        self.assertEqual(original, (ROOT / "rv32_btb.sv").read_text())
        self.assertEqual(digest(original), record["candidate_btb_sha256"])
        self.assertNotIn("reg return_entry", original)

    def simulate(self, index, history, depth, mutation=None):
        candidate = (ROOT / "rv32_btb.sv").read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(candidate.count(before), 1)
            candidate = candidate.replace(before, after)
        original = (PARENT / "rv32_btb.sv").read_text()
        self.assertEqual(original.count("module rv32_btb #("), 1)
        original = original.replace("module rv32_btb #(", "module rv32_btb_reference #(")
        with tempfile.TemporaryDirectory(prefix="return-metadata-") as temporary:
            work = Path(temporary)
            (work / "candidate.sv").write_text(candidate)
            (work / "reference.sv").write_text(original)
            command = ["iverilog", "-g2012", "-s", "return_metadata_tb",
                       "-Preturn_metadata_tb.INDEX_BITS=" + str(index), "-Preturn_metadata_tb.HISTORY_BITS=" + str(history),
                       "-Preturn_metadata_tb.STACK_DEPTH=" + str(depth), "-o", str(work / "test.vvp"),
                       str(work / "candidate.sv"), str(work / "reference.sv"), str(ROOT / "return_metadata_tb.sv")]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            for diagnostic in compiled.stderr.splitlines():
                self.assertRegex(diagnostic, r"^.*\.sv:\d+: warning: Attributes are not supported on net declaration assignments and will be discarded\.$")
            executed = subprocess.run(["vvp", str(work / "test.vvp")], capture_output=True, text=True, timeout=180)
            output = executed.stdout + executed.stderr
            if mutation:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL metadata", output)
            else:
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn("outputs=24000", output)
                self.assertIn("PASS metadata", output)
            print(output.strip(), flush=True)

    def test_clocked_differential(self):
        for configuration in ((4, 1, 0), (4, 1, 1), (4, 3, 1), (4, 4, 2), (8, 3, 1)):
            with self.subTest(configuration=configuration):
                self.simulate(*configuration)

    def test_compiled_faults_rejected(self):
        mutations = (
            ("history[update_index]<={{(HISTORY_BITS-1){1'b0}},update_return};", "history[update_index]<={{(HISTORY_BITS-1){1'b0}},update_taken};"),
            ("if (!update_conditional)", "if (!update_conditional && allocate_entry)"),
            ("history[fetch_index][0]", "history[fetch_index][HISTORY_BITS-1]"),
            ("stack_available && history[fetch_index][0] && !conditional[fetch_index]", "stack_available && history[fetch_index][0]"),
            ("history[update_index]<={{(HISTORY_BITS-1){1'b0}},update_taken};", "history[update_index]<={{(HISTORY_BITS-1){1'b0}},update_return};"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate(4, 3, 1, mutation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
