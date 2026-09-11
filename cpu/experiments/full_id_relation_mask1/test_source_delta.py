import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_decode_payload1"


def checksum(text):
    return hashlib.sha256(text.encode()).hexdigest().upper()


def validate(core, predictor):
    record = json.loads((ROOT / "change-receipt.json").read_text())
    parent = (PARENT / "rv32_core.sv").read_text()
    if record["parent"] != PARENT.name or checksum(parent) != record["parent_core_sha256"]:
        raise ValueError("Wrong parent core")
    if len(record["substitutions"]) != 3:
        raise ValueError("Wrong id_relation_mask substitution count")
    expected = parent
    for before, after in record["substitutions"]:
        if expected.count(before) != 1:
            raise ValueError("Ambiguous id_relation_mask substitution")
        expected = expected.replace(before, after)
    if core != expected or checksum(core) != record["core_sha256"]:
        raise ValueError("Unexpected core delta")
    if predictor != (PARENT / "rv32_btb.sv").read_text() or checksum(predictor) != record["btb_sha256"]:
        raise ValueError("Predictor changed")


class SourceDeltaTests(unittest.TestCase):
    def texts(self):
        return (ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text()

    def test_exact_id_relation_mask_change(self):
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
            validate(core.replace("if(id_payload_load)", "if(1'b1)"), predictor)

    def test_predictor_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Predictor changed"):
            validate(core, predictor + chr(10))


if __name__ == "__main__":
    unittest.main(verbosity=2)
