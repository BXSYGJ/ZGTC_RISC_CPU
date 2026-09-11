import unittest
from unittest.mock import patch

import audit_clock_firmware as audit


class ClockFirmwareTests(unittest.TestCase):
    def test_all_four_firmwares(self):
        result = audit.audit_firmware()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["firmwares"]), 4)

    def test_corrupted_compiler_or_manifest_rejected(self):
        original = audit.load
        changes = (
            ("receipt.json", lambda record: record["compile_command"].append("-flto")),
            ("receipt.json", lambda record: record["source_hashes"].pop("sw/platform.h")),
            ("receipt.json", lambda record: record.update(passed=False)),
            ("receipt.json", lambda record: record["outputs"].pop(next(iter(record["outputs"])))),
            (".build.json", lambda record: record.update(ClockHz=151200000)),
        )
        for index, (suffix, change) in enumerate(changes):
            def changed(path):
                record = original(path)
                if audit.ROOT in path.parents and path.name.endswith(suffix):
                    change(record)
                return record
            with self.subTest(index=index), patch.object(audit, "load", side_effect=changed):
                with self.assertRaises(ValueError):
                    audit.audit_firmware()


if __name__ == "__main__":
    unittest.main(verbosity=2)
