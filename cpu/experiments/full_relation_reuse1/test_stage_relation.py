import unittest
from unittest.mock import patch

import stage_relation_physical as stage


class RelationStageTests(unittest.TestCase):
    def changed(self, target, edit):
        original = stage.read_json
        def read(path):
            record = original(path)
            if path == target:
                edit(record)
            return record
        return patch.object(stage, "read_json", side_effect=read)

    def test_current_functional_matrix(self):
        record = stage.validate_functional()
        self.assertEqual(record["core_runs"], 16)
        self.assertEqual(record["compiled_faults"], 4)

    def test_incomplete_regression_and_outputs_rejected(self):
        target = stage.ROOT / "build/core-regressions-coverage-groups/manifest.json"
        edits = (lambda record: record.update(passed=False), lambda record: record["runs"].pop(),
                 lambda record: record["source_hashes"].pop("rtl/rv32_core.sv"),
                 lambda record: record["outputs"].pop("cached-p0-l0-12345678.trace"))
        for index, edit in enumerate(edits):
            with self.subTest(index=index), self.changed(target, edit), self.assertRaises(ValueError):
                stage.validate_functional()

    def test_coverage_must_match_raw_logs(self):
        target = stage.ROOT / "build/core-regressions-coverage-groups/manifest.json"
        with self.changed(target, lambda record: record["runs"][0]["relation_coverage"].update(mem=999)):
            with self.assertRaisesRegex(ValueError, "Relation coverage differs from log"):
                stage.validate_functional()

    def test_incomplete_fault_evidence_rejected(self):
        target = stage.ROOT / "build/relation-tests-186e1eff/manifest.json"
        edits = (lambda record: record.update(passed=False),
                 lambda record: record["inputs"].pop(next(iter(record["inputs"]))),
                 lambda record: record["outputs"].pop("case-1/execute.log"))
        for index, edit in enumerate(edits):
            with self.subTest(index=index), self.changed(target, edit), self.assertRaises(ValueError):
                stage.validate_functional()

    def test_accepted_mutation_rejected(self):
        target = stage.ROOT / "build/relation-tests-186e1eff/case-1/invocation.json"
        with self.changed(target, lambda record: record.update(execute_exit=0)):
            with self.assertRaisesRegex(ValueError, "Compiled relation fault was not rejected"):
                stage.validate_functional()

    def test_observer_changes_rejected(self):
        target = stage.ROOT / "observer-receipt.json"
        with self.changed(target, lambda record: record["core_tb.sv"].update(observer_sha256="0" * 64)):
            with self.assertRaisesRegex(ValueError, "Relation observer changed"):
                stage.validate_functional()

    def test_current_shorts_and_bad_command(self):
        bound = stage.parent_audit.binding()
        bound["physical_source_hashes"] = {name: stage.digest(stage.candidate_source(name)) for name in bound["physical_source_hashes"]}
        stage.validate_shorts(bound)
        target = stage.ROOT / "build/v0/manifest.json"
        with self.changed(target, lambda record: record["compile_command"].append("-GBAUD=99")):
            with self.assertRaisesRegex(ValueError, "Short compiler command differs"):
                stage.validate_shorts(bound)


if __name__ == "__main__":
    unittest.main(verbosity=2)
