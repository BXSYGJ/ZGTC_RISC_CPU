import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_raw_relation_payload"


def checksum(text):
    return hashlib.sha256(text.encode()).hexdigest().upper()


def validate(core, predictor):
    record = json.loads((ROOT / "change-receipt.json").read_text())
    parent = (PARENT / "rv32_core.sv").read_text()
    if record["parent"] != PARENT.name or checksum(parent) != record["parent_core_sha256"]:
        raise ValueError("Wrong parent core")
    if parent.count(".RETURN_STACK_DEPTH(2)") != 1:
        raise ValueError("Ambiguous parent stack depth")
    if core != parent.replace(".RETURN_STACK_DEPTH(2)", ".RETURN_STACK_DEPTH(1)"):
        raise ValueError("Unexpected core delta")
    if checksum(core) != record["core_sha256"]:
        raise ValueError("Core checksum mismatch")
    if predictor != (PARENT / "rv32_btb.sv").read_text() or checksum(predictor) != record["btb_sha256"]:
        raise ValueError("Predictor changed")
    if record["substitutions"] != [[".RETURN_STACK_DEPTH(2)", ".RETURN_STACK_DEPTH(1)"]]:
        raise ValueError("Wrong delta receipt")


class SourceDeltaTests(unittest.TestCase):
    def texts(self):
        return (ROOT / "rv32_core.sv").read_text(), (ROOT / "rv32_btb.sv").read_text()

    def test_exact_one_entry_change(self):
        validate(*self.texts())

    def test_wrong_depth_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Unexpected core delta"):
            validate(core.replace(".RETURN_STACK_DEPTH(1)", ".RETURN_STACK_DEPTH(0)"), predictor)

    def test_other_core_logic_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Unexpected core delta"):
            validate(core + "\n", predictor)

    def test_predictor_change_rejected(self):
        core, predictor = self.texts()
        with self.assertRaisesRegex(ValueError, "Predictor changed"):
            validate(core, predictor + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
