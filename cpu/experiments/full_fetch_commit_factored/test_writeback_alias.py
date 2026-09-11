import re
import unittest

import audit_fetch_ila as audit


class WritebackAliasTests(unittest.TestCase):
    stage = audit.ROOT / "build/ila/fetch-commit-seed1"
    actual = "board/soc/unused_pipeline_valid[4]"
    canonical = "board/soc/core/board/unused_trace_valid"

    def fixture(self):
        netlist, fic, output, probe = tuple((self.stage / name).read_text(encoding="utf-8-sig") for name in
                                          ("netlist.v", "cpu-remapped.fic", "verify-remapped.stdout.txt", "probe.stdout.txt"))
        self.assertNotIn("Project.unit<0>.dataChannel<36>=", fic)
        fic += "\nProject.unit<0>.dataChannel<36>=" + self.actual + "\n"
        return netlist, fic, output, probe

    def test_native_port_and_driver_prove_alias(self):
        fic, output, aliases = audit.normalize_mapping(*self.fixture())
        self.assertIn("Project.unit<0>.dataChannel<36>=" + self.canonical, fic)
        self.assertEqual(aliases[self.actual], self.canonical)
        with self.assertRaisesRegex(ValueError, "Actual Inserter Data map mismatch"):
            audit.shared.validate_config(fic, output)

    def test_original_incomplete_mapping_remains_rejected(self):
        values = tuple((self.stage / name).read_text(encoding="utf-8-sig") for name in
                       ("netlist.v", "cpu-remapped.fic", "verify-remapped.stdout.txt", "probe.stdout.txt"))
        with self.assertRaisesRegex(ValueError, "Missing writeback-valid channel"):
            audit.normalize_mapping(*values)

    def test_wrong_writeback_driver_rejected(self):
        netlist, fic, output, probe = self.fixture()
        before = ".Q (" + chr(92) + "board/unused_trace_valid )"
        self.assertEqual(netlist.count(before), 1)
        with self.assertRaisesRegex(ValueError, "Wrong writeback register driver"):
            audit.normalize_mapping(netlist.replace(before, ".Q (pipeline_valid[3])"), fic, output, probe)

    def test_wrong_core_port_rejected(self):
        netlist, fic, output, probe = self.fixture()
        module = re.findall(r"\bmodule rv32_soc\b(.*?)\bendmodule\b", netlist, re.S)[0]
        instance = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", module, re.S)[0]
        before = "." + chr(92) + "board/unused_trace_valid  (unused_pipeline_valid[4])"
        self.assertEqual(instance.count(before), 1)
        changed_instance = instance.replace(before, "." + chr(92) + "board/unused_trace_valid  (unused_pipeline_valid[3])")
        changed = netlist.replace(instance, changed_instance)
        with self.assertRaisesRegex(ValueError, "Wrong writeback alias connection"):
            audit.normalize_mapping(changed, fic, output, probe)

    def test_missing_or_duplicate_probe_rejected(self):
        netlist, fic, output, probe = self.fixture()
        rows = [row for row in probe.splitlines() if re.match(r"^\d+\s*:\s*" + re.escape(self.actual) + r"\s+", row)]
        self.assertEqual(len(rows), 1)
        for changed in (probe.replace(rows[0], ""), probe + "\n" + rows[0] + "\n"):
            with self.assertRaisesRegex(ValueError, "Unverified or ambiguous writeback alias"):
                audit.normalize_mapping(netlist, fic, output, changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
