import re
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_clock_ila as audit


class ClockIlaTests(unittest.TestCase):
    stage = audit.ROOT / "build/ila/timer-clock153-seed1"

    def changed_text(self, target, transform):
        original = Path.read_text
        def read(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            return transform(value) if path.resolve() == target.resolve() else value
        return patch.object(Path, "read_text", read)

    def changed_json(self, target, transform):
        original = audit.load
        def load(path):
            value = original(path)
            if path.resolve() == target.resolve():
                transform(value)
            return value
        return patch.object(audit, "load", side_effect=load)

    def mapping_inputs(self):
        return tuple((self.stage / name).read_text(encoding="utf-8-sig") for name in
                     ("netlist.v", "cpu-remapped.fic", "verify-remapped.stdout.txt", "probe.stdout.txt"))

    def test_current_complete_binding(self):
        bound = audit.binding()
        self.assertEqual(bound["clock_hz"], 153000000)
        self.assertEqual(len(bound["physical_source_hashes"]), 20)
        self.assertEqual(len(bound["short_manifest_sha256"]), 2)
        self.assertEqual(bound["firmware_sha256"], "6DAAE1B97ED63CBD65BFF5A8F6BD15FC4E67378BA3316D790911EF5CF5D545CD")

    def test_wrong_project_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong clock physical project"):
            audit.binding(audit.ROOT.parent / "full_timer_prefix16/build/pds/unrelated")

    def test_wrong_clock_and_hardware_parameter_rejected(self):
        for before, after in (("153000000", "151200000"), (".ENABLE_CACHE(1)", ".ENABLE_CACHE(0)")):
            with self.subTest(before=before), self.changed_text(audit.SOURCE / "pds_soc_top.v", lambda value: value.replace(before, after)):
                with self.assertRaises(ValueError):
                    audit.binding()

    def test_wrong_firmware_rejected(self):
        target = audit.ROOT / "build/coremark_v0_i6000_p2700000_f153000000_rv32gcc_rv32im_O3_unroll_relax.build.json"
        for values in ({"ClockHz": 151200000}, {"HexSha256": "0" * 64}):
            with self.subTest(values=values), self.changed_json(target, lambda value: value.update(values)):
                with self.assertRaisesRegex(ValueError, "Wrong 153 MHz physical firmware"):
                    audit.binding()

    def test_actual_native_mapping_complete(self):
        fic, output, aliases = audit.normalize_mapping(*self.mapping_inputs())
        result = audit.shared.validate_config(fic, output)
        self.assertEqual((result["data_channels"], result["trigger_channels"], result["depth"]), (42, 33, 1024))
        self.assertEqual(aliases, {"board/soc/core/pipeline_valid[3]": "board/soc/unused_pipeline_valid[3]"})

    def test_missing_and_duplicate_native_probe_rejected(self):
        netlist, fic, output, probe = self.mapping_inputs()
        for index in range(4):
            name = "board/soc/core/pipeline_valid[" + str(index) + "]"
            rows = [row for row in probe.splitlines() if re.match(r"^\d+\s*:\s*" + re.escape(name) + r"\s+", row)]
            self.assertEqual(len(rows), 1)
            for changed in (probe.replace(rows[0], ""), probe + "\n" + rows[0] + "\n"):
                with self.subTest(index=index), self.assertRaisesRegex(ValueError, "Unverified or ambiguous pipeline alias"):
                    audit.normalize_mapping(netlist, fic, output, changed)

    def test_wrong_pipeline_register_drivers_rejected(self):
        netlist, fic, output, probe = self.mapping_inputs()
        for index in range(4):
            before = ".Q (pipeline_valid[" + str(index) + "])"
            self.assertEqual(netlist.count(before), 1)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "Wrong pipeline register driver"):
                audit.normalize_mapping(netlist.replace(before, ".Q (not_the_pipeline_register)"), fic, output, probe)

    def test_missing_native_data_channel_rejected(self):
        netlist, fic, output, probe = self.mapping_inputs()
        for index in range(32, 36):
            rows = output.splitlines()
            prefix = "Data Channel " + str(index) + ":"
            self.assertEqual(sum(row.startswith(prefix) for row in rows), 1)
            changed = "\n".join(row for row in rows if not row.startswith(prefix))
            canonical_fic, canonical_output, _ = audit.normalize_mapping(netlist, fic, changed, probe)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "Actual Inserter Data map mismatch"):
                audit.shared.validate_config(canonical_fic, canonical_output)

    def test_unprobed_soc_alias_rejected(self):
        netlist, fic, output, probe = self.mapping_inputs()
        before = "board/soc/core/pipeline_valid[3]"
        after = "board/soc/unused_pipeline_valid[3]"
        with self.assertRaisesRegex(ValueError, "Unverified or ambiguous pipeline alias"):
            audit.normalize_mapping(netlist, fic.replace(before, after), output.replace(before, after), probe)

    def test_actual_physical_result_stays_rejected(self):
        with patch.object(audit, "parse_ila_reports", wraps=audit.parse_ila_reports) as parser:
            result = audit.qualify(self.stage)
        self.assertEqual(parser.call_args.args[2], 153000000)
        self.assertEqual(result["setup_wns_ns"], -0.223)
        self.assertEqual(result["resources"]["post_route_luts"], 9502)
        self.assertFalse(result["physical_timing_passed"])
        self.assertFalse(result["resource_efficiency_qualified"])
        self.assertFalse(result["hardware_validated"])
        self.assertFalse(result["full_score_qualified"])
        self.assertIsNone(result["coremark_score"])

    def test_incomplete_or_mismatched_invocation_rejected(self):
        changes = (
            lambda value: value.update(ExitCode=None),
            lambda value: value.update(PlacementSeed=2),
            lambda value: value.update(WorkingDirectory=str(audit.ROOT)),
            lambda value: value["Inputs"].pop("board.fdc"),
            lambda value: value["Inputs"].update({"source.adf": "0" * 64}),
            lambda value: value.update(FinishedUtc=value["StartedUtc"]),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json(self.stage / "invocation.json", change):
                with self.assertRaises(ValueError):
                    audit.qualify(self.stage)


if __name__ == "__main__":
    unittest.main(verbosity=2)
