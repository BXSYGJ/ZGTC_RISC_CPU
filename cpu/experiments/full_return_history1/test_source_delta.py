import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_id_relation_mask1"


def checksum(text):
    return hashlib.sha256(text.encode()).hexdigest().upper()


def validate(core, predictor):
    record = json.loads((ROOT / "change-receipt.json").read_text())
    parent_core = (PARENT / "rv32_core.sv").read_text()
    parent_btb = (PARENT / "rv32_btb.sv").read_text()
    if record["parent"] != PARENT.name or checksum(parent_core) != record["parent_core_sha256"]:
        raise ValueError("Wrong parent core")
    if record["substitutions"] or core != parent_core or checksum(core) != record["core_sha256"]:
        raise ValueError("Unexpected core delta")
    if checksum(parent_btb) != record["parent_btb_sha256"] or len(record["predictor_substitutions"]) != 4:
        raise ValueError("Wrong predictor parent or delta count")
    expected = parent_btb
    for before, after in record["predictor_substitutions"]:
        if expected.count(before) != 1:
            raise ValueError("Ambiguous predictor substitution")
        expected = expected.replace(before, after)
    if predictor != expected or checksum(predictor) != record["btb_sha256"]:
        raise ValueError("Predictor changed")
    if set(record["files"]) != {"rv32_core.sv", "rv32_btb.sv"}:
        raise ValueError("Incomplete qualified ancestry")
    for filename, ancestry in record["files"].items():
        original = (ROOT.parent / "full_redirect_clock151200/rtl" / filename).read_text()
        if checksum(original) != ancestry["parent_sha256"]:
            raise ValueError("Qualified ancestor changed")
        for before, after in ancestry["substitutions"]:
            if original.count(before) != 1:
                raise ValueError("Ambiguous qualified ancestry")
            original = original.replace(before, after)
        current = core if filename == "rv32_core.sv" else predictor
        if current != original or checksum(current) != ancestry["candidate_sha256"]:
            raise ValueError("Qualified ancestry differs")


class SourceDeltaTests(unittest.TestCase):
    def texts(self):
        return (ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text()

    def test_exact_return_history_change(self):
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
