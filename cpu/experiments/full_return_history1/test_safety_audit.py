import json
from pathlib import Path
import unittest
from unittest.mock import patch

import run_safety as safety


class SafetyEvidenceTests(unittest.TestCase):
    def test_current_evidence(self):
        self.assertEqual(safety.audit()["methods"], 24)

    def test_changed_current_source_rejected(self):
        with patch.object(safety, "inputs", return_value={}):
            with self.assertRaisesRegex(ValueError, "Safety source set changed"):
                safety.audit()

    def test_changed_log_rejected(self):
        original = safety.digest
        def changed(path):
            return "0" * 64 if path.name == "test_prefetch_valid.py.log" else original(path)
        with patch.object(safety, "digest", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Safety output changed"):
                safety.audit()

    def test_incomplete_manifest_rejected(self):
        original = Path.read_text
        def changed(path, *arguments, **keywords):
            text = original(path, *arguments, **keywords)
            if path == safety.OUTPUT / "manifest.json":
                record = json.loads(text)
                record["passed"] = False
                return json.dumps(record)
            return text
        with patch.object(Path, "read_text", changed):
            with self.assertRaisesRegex(ValueError, "run incomplete"):
                safety.audit()

    def test_missing_suite_log_rejected(self):
        original = Path.read_text
        def changed(path, *arguments, **keywords):
            text = original(path, *arguments, **keywords)
            if path == safety.OUTPUT / "manifest.json":
                record = json.loads(text)
                record["outputs"].pop("test_prefetch_valid.py.log")
                return json.dumps(record)
            return text
        with patch.object(Path, "read_text", changed):
            with self.assertRaisesRegex(ValueError, "Incomplete safety logs"):
                safety.audit()

    def test_missing_raw_completion_rejected(self):
        original = Path.read_text
        def changed(path, *arguments, **keywords):
            text = original(path, *arguments, **keywords)
            return text.replace("OK", "NOT_COMPLETED") if path.name == "test_prefetch_valid.py.log" else text
        with patch.object(Path, "read_text", changed):
            with self.assertRaisesRegex(ValueError, "Raw unittest completion missing"):
                safety.audit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
