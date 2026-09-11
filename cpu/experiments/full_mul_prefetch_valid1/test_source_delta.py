import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_return_stack1"


def checksum(text):
    return hashlib.sha256(text.encode()).hexdigest().upper()


def validate(core, predictor):
    record = json.loads((ROOT / "change-receipt.json").read_text())
    parent = (PARENT / "rv32_core.sv").read_text()
    if record["parent"] != PARENT.name or checksum(parent) != record["parent_core_sha256"]:
        raise ValueError("Wrong parent core")
    if len(record["substitutions"]) != 4:
        raise ValueError("Wrong prefetch substitution count")
    expected = parent
    for before, after in record["substitutions"]:
        if expected.count(before) != 1:
            raise ValueError("Ambiguous prefetch substitution")
        expected = expected.replace(before, after)
    if core != expected or checksum(core) != record["core_sha256"]:
        raise ValueError("Unexpected core delta")
    if predictor != (PARENT / "rv32_btb.sv").read_text() or checksum(predictor) != record["btb_sha256"]:
        raise ValueError("Predictor changed")


class SourceDeltaTests(unittest.TestCase):
    def texts(self):
        return (ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text()

    def test_exact_prefetch_change(self):
        validate(*self.texts())

    def test_wrong_depth_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Unexpected core delta"):
            validate(core.replace(".RETURN_STACK_DEPTH(1)", ".RETURN_STACK_DEPTH(2)"), predictor)

    def test_other_core_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Unexpected core delta"):
            validate(core + chr(10), predictor)

    def test_availability_gate_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Unexpected core delta"):
            validate(core.replace("mul_id_a_available && mul_id_b_available", "mul_id_a_available"), predictor)

    def test_predictor_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Predictor changed"):
            validate(core, predictor + chr(10))


if __name__ == "__main__":
    unittest.main(verbosity=2)
