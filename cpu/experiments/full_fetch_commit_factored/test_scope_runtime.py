import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_fetch_scope_run as audit

DIRECTORY = audit.ROOT / "build/scope-current/20260911-105053-71d3ebca"


class ScopeRuntimeTests(unittest.TestCase):
    def test_actual_complete_application(self):
        result = audit.audit(DIRECTORY)
        self.assertTrue(result["simulation_passed"])
        self.assertFalse(result["hardware_validated"])
        self.assertEqual({capture["trigger_mask"] for capture in result["captures"]}, {1, 2})
        self.assertEqual(sum(result["counter_jumps_used"]), 4590000000)

    def test_incomplete_mislabeled_or_wrong_timebase_rejected(self):
        original = audit.load
        for field, value in (("passed", False), ("hardware_validated", True), ("host_timeout_seconds", 1), ("simulation_overrides", {}), ("runner_sha256", "wrong")):
            with self.subTest(field=field):
                def altered(path):
                    record = copy.deepcopy(original(path))
                    if path == DIRECTORY / "manifest.json":
                        record[field] = value
                    return record
                with patch.object(audit, "load", side_effect=altered), self.assertRaises(ValueError):
                    audit.audit(DIRECTORY)

    def test_generated_bench_cannot_hide_counter_jump_changes(self):
        original = Path.read_text
        def altered(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == DIRECTORY / "scope_tb.sv":
                return result.replace("64'd295032704", "64'd1")
            return result
        with patch.object(Path, "read_text", altered), self.assertRaisesRegex(ValueError, "Compiled scope bench differs"):
            audit.audit(DIRECTORY)

    def test_terminal_and_raw_capture_corruption_rejected(self):
        output = (DIRECTORY / "execute.log").read_text(encoding="utf-8")
        uart = (DIRECTORY / "scope.uart").read_text(encoding="utf-8")
        for log, capture in ((output + "\nFATAL: injected failure", uart), (output, uart.replace("clock=091e9840", "clock=09032400")), (output, uart.replace("late=00000000", "late=00000001"))):
            with self.subTest(capture_tail=capture[-70:]), self.assertRaises(ValueError):
                audit.runner.validate_output(log, capture)


if __name__ == "__main__":
    unittest.main(verbosity=2)
