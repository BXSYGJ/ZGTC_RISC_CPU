import unittest
from unittest.mock import patch

import audit_clock_shorts as audit


class ClockShortTests(unittest.TestCase):
    def test_current_pair(self):
        result = audit.audit_shorts()
        self.assertEqual(sorted(run["result"]["cycles"] for run in result["runs"]), [3000565, 3001255])

    def test_incomplete_or_changed_manifest_rejected(self):
        original = audit.load
        changes = (
            lambda record: record.update(SimulationPassed=False),
            lambda record: record["SourceSnapshot"].pop("rtl/rv32_uart.sv"),
            lambda record: record["CompileCommand"].append("-GCLOCK_HZ=153000000"),
            lambda record: record.update(SimulationClockHz=153000000),
            lambda record: record.update(CompletedUtc=None),
        )
        for index, change in enumerate(changes):
            def changed(path):
                record = original(path)
                if path.name == "manifest.json" and audit.ROOT in path.parents:
                    change(record)
                return record
            with self.subTest(index=index), patch.object(audit, "load", side_effect=changed):
                with self.assertRaises(ValueError):
                    audit.audit_shorts()

    def test_result_not_matching_uart_rejected(self):
        original = audit.load
        def changed(path):
            record = original(path)
            if path.name == "result.json" and audit.ROOT in path.parents:
                record["cycles"] += 1
            return record
        with patch.object(audit, "load", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Short raw UART and stored result differ"):
                audit.audit_shorts()


if __name__ == "__main__":
    unittest.main(verbosity=2)
