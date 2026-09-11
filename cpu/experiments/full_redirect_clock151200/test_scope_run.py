import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_scope_run
from audit_scope_run import ROOT, audit

RUN = ROOT / "build/scope-current/20260911-010153-3367fed2"


class ScopeRuntimeTests(unittest.TestCase):
    def test_completed_actual_application(self):
        result = audit(RUN)
        self.assertTrue(result["simulation_passed"])
        self.assertFalse(result["hardware_validated"])
        self.assertEqual(len(result["captures"]), 2)

    def test_changed_hashed_artifacts_rejected(self):
        original = audit_scope_run.digest
        targets = (ROOT / "run_scope_current.py", ROOT / "scripts/scope_decode.py", RUN / "scope_tb.sv",
                   RUN / "scope.uart", RUN / "execute.log", RUN / "scope.vvp", ROOT / "rtl/rv32_core.sv")
        for target in targets:
            def altered(filename):
                return "0" * 64 if filename.resolve() == target.resolve() else original(filename)
            with self.subTest(target=str(target)), patch.object(audit_scope_run, "digest", altered):
                with self.assertRaises(ValueError):
                    audit(RUN)

    def test_manifest_labels_timebase_and_summaries_rejected(self):
        filename = RUN / "manifest.json"
        original_read = Path.read_text
        original = json.loads(original_read(filename, encoding="utf-8"))
        mutations = [("passed", False), ("hardware_validated", True), ("captures", []),
                     ("simulation_overrides", dict(original["simulation_overrides"], uart_injected_bit_cycles=16071)),
                     ("physical_parameters", dict(original["physical_parameters"], CLOCK_HZ=154285714)),
                     ("input_hashes", {name: value for name, value in original["input_hashes"].items() if name != "rtl/rv32_core.sv"})]
        for field, value in mutations:
            changed = copy.deepcopy(original)
            changed[field] = value
            def altered_read(path, *arguments, **keywords):
                return json.dumps(changed) if path.resolve() == filename.resolve() else original_read(path, *arguments, **keywords)
            with self.subTest(field=field), patch.object(Path, "read_text", altered_read):
                with self.assertRaises(ValueError):
                    audit(RUN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
