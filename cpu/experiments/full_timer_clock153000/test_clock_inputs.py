import unittest
from unittest.mock import patch

import audit_clock_inputs as audit


class ClockInputTests(unittest.TestCase):
    def test_current_complete_inputs(self):
        result = audit.audit_inputs()
        self.assertEqual(len(result["physical_source_hashes"]), 20)
        self.assertEqual(len(result["firmware_sources"]), 12)

    def test_clock_only_configuration(self):
        config = audit.load(audit.ROOT / "configuration.json")
        for field, value in (("ClockHz", 151200000), ("CacheSetBits", 5), ("EnableM", 0), ("LoadUseBubble", 0)):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Unexpected clock configuration change"):
                audit.validate_configuration(dict(config, **{field: value}))

    def test_missing_or_changed_inventory_rejected(self):
        original = audit.load
        changes = (
            lambda record: record["physical_source_hashes"].pop("rtl/rv32_uart.sv"),
            lambda record: record["physical_source_hashes"].update({"rtl/rv32_core.sv": "0" * 64}),
            lambda record: record["firmware_sources"].pop("sw/platform.h"),
            lambda record: record["support_scripts"].pop("sim/coremark_compiled.cpp"),
            lambda record: record.update(generator_sha256="0" * 64),
        )
        for index, change in enumerate(changes):
            def changed(path):
                record = original(path)
                if path.name == "source-inputs.json":
                    change(record)
                return record
            with self.subTest(index=index), patch.object(audit, "load", side_effect=changed):
                with self.assertRaises(ValueError):
                    audit.audit_inputs()


if __name__ == "__main__":
    unittest.main(verbosity=2)
