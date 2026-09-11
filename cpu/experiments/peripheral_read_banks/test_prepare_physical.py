import unittest
from unittest.mock import patch

import stage_banked_physical as preparation


class PeripheralStageTests(unittest.TestCase):
    def test_current_complete_functional_evidence(self):
        result = preparation.validate_functional()
        self.assertEqual(len(result["source_hashes"]), 8)

    def test_incomplete_or_tampered_evidence_rejected(self):
        changes = (
            lambda record: record.update(passed=False),
            lambda record: record.update(tests_run=2),
            lambda record: record["sources"].pop(next(iter(record["sources"]))),
            lambda record: record["outputs"].pop("case-6/testbench.sv"),
            lambda record: record["outputs"].update({"case-6/candidate.sv": "0" * 64}),
        )
        original = preparation.read_json
        for index, change in enumerate(changes):
            def changed(path):
                record = original(path)
                if path.name == "manifest.json":
                    change(record)
                return record
            with self.subTest(index=index), patch.object(preparation, "read_json", side_effect=changed):
                with self.assertRaises(ValueError):
                    preparation.validate_functional()

    def test_failed_positive_or_missing_negative_rejected(self):
        original = preparation.read_json
        for label, case, fields in (("positive", "case-6", {"execute_exit": 1}),
                                    ("negative", "case-1", {"execute_exit": 0}),
                                    ("mutation", "case-1", {"mutation": None})):
            def changed(path):
                record = original(path)
                if path.name == "invocation.json" and path.parent.name == case:
                    record.update(fields)
                return record
            with self.subTest(label=label), patch.object(preparation, "read_json", side_effect=changed):
                with self.assertRaises(ValueError):
                    preparation.validate_functional()


if __name__ == "__main__":
    unittest.main(verbosity=2)
