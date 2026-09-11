import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import audit_full_ila as audit


class FullIlaAuditTests(unittest.TestCase):
    def test_current_candidate_binding(self):
        result = audit.binding()
        self.assertEqual(result["clock_hz"], 151200000)
        self.assertEqual(len(result["physical_source_hashes"]), 20)

    def test_missing_snapshot_entry_rejected(self):
        snapshot = audit.read_json(audit.SOURCE / "source-snapshot.json")
        expected = dict(snapshot["Files"])
        del snapshot["Files"]["rtl/rv32_uart.sv"]
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            audit.validate_inventory(snapshot, expected, audit.SOURCE)

    def test_wrong_snapshot_root_rejected(self):
        snapshot = audit.read_json(audit.SOURCE / "source-snapshot.json")
        snapshot["Root"] = str(audit.BASE)
        with self.assertRaisesRegex(ValueError, "source root"):
            audit.validate_inventory(snapshot, snapshot["Files"], audit.SOURCE)

    def test_changed_captured_rtl_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            (source / "source").mkdir()
            filename = source / "source/rtl.sv"
            filename.write_text("original", encoding="utf-8")
            expected = {"rtl.sv": audit.digest(filename)}
            snapshot = {"Root": str(source / "source"), "Files": expected}
            filename.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Captured source changed"):
                audit.validate_inventory(snapshot, expected, source)

    def test_wrong_project_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong PDS project"):
            audit.binding(audit.BASE / "build/pds/unrelated")

    def test_non_predictor_delta_rejected(self):
        original = audit.read_json
        def changed(path):
            result = original(path)
            if path.name == "physical-project-complete-inputs.json":
                result["source_hashes"]["rtl/rv32_uart.sv"] = "0" * 64
            return result
        with patch.object(audit, "read_json", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Unexpected physical delta"):
                audit.binding()

    def test_firmware_stage_change_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            source = stage / "original"
            copies = {"source.adf": "synthesize/pds_soc_top_syn.adf", "netlist.v": "synthesize/pds_soc_top_syn.vm", "firmware.hex": "firmware.hex"}
            for target, relative in copies.items():
                original = source / relative
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_text(target, encoding="utf-8")
                (stage / target).write_text(target, encoding="utf-8")
            (stage / "firmware.hex").write_text("wrong", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Staged input differs: firmware.hex"):
                audit.validate_stage_inputs(stage, source)

    def test_initial_incomplete_inserter_map_rejected(self):
        stage = audit.ROOT / "build/ila/two-way-seed1"
        with self.assertRaisesRegex(ValueError, "Missing pipeline data channel"):
            audit.mapping(stage)


    def test_native_alias_mapping_complete(self):
        stage = audit.ROOT / "build/ila/two-way-seed1-native-alias"
        result = audit.mapping(stage)
        self.assertEqual((result["data_channels"], result["trigger_channels"], result["depth"]), (42, 33, 1024))

    def test_wrong_mem_valid_alias_bit_rejected(self):
        stage = audit.ROOT / "build/ila/two-way-seed1-native-alias"
        netlist = (stage / "netlist.v").read_text(encoding="utf-8-sig")
        fic = (stage / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
        output = (stage / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")
        before = r"{\core_pipeline_valid[4]_floating , unused_pipeline_valid[3],"
        self.assertEqual(netlist.count(before), 1)
        with self.assertRaisesRegex(ValueError, "alias wiring differs"):
            audit.normalize_candidate_mapping(netlist.replace(before, before.replace("unused_pipeline_valid[3]", "unused_pipeline_valid[2]")), fic, output)

    def test_missing_actual_native_channel_rejected(self):
        stage = audit.ROOT / "build/ila/two-way-seed1-native-alias"
        netlist = (stage / "netlist.v").read_text(encoding="utf-8-sig")
        fic = (stage / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
        output = (stage / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig")
        rows = output.splitlines()
        self.assertEqual(sum(row.startswith("Data Channel 35:") for row in rows), 1)
        output = "\n".join(row for row in rows if not row.startswith("Data Channel 35:"))
        fic, output, _ = audit.normalize_candidate_mapping(netlist, fic, output)
        with self.assertRaisesRegex(ValueError, "Actual Inserter Data map mismatch"):
            audit.validate_config(fic, output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
