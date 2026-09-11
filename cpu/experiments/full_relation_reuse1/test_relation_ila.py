import unittest
from unittest.mock import patch

import audit_relation_ila as audit


class RelationIlaTests(unittest.TestCase):
    def test_current_complete_binding(self):
        result = audit.binding()
        self.assertEqual(len(result["physical_source_hashes"]), 20)
        self.assertEqual(result["clock_hz"], 151200000)
        self.assertEqual(result["physical_source_hashes"]["rtl/rv32_core.sv"], audit.digest(audit.ROOT / "rv32_core.sv"))

    def test_wrong_project_rejected(self):
        with self.assertRaisesRegex(ValueError, "Wrong PDS project"):
            audit.binding(audit.PARENT / "build/pds/unrelated")

    def changed_json(self, filename, change):
        module = audit.staging if filename == "manifest.json" else audit
        original = module.read_json
        def read(path):
            value = original(path)
            if path.name == filename and (filename != "manifest.json" or path.parent.name in ("v0", "v1")):
                change(value)
            return value
        return patch.object(module, "read_json", side_effect=read)

    def test_missing_inventory_rejected(self):
        with self.changed_json("physical-project-complete-inputs.json", lambda record: record["source_hashes"].pop("rtl/rv32_uart.sv")):
            with self.assertRaisesRegex(ValueError, "Incomplete physical"):
                audit.binding()

    def test_unexpected_uart_change_rejected(self):
        with self.changed_json("physical-project-complete-inputs.json", lambda record: record["source_hashes"].update({"rtl/rv32_uart.sv": "0" * 64})):
            with self.assertRaisesRegex(ValueError, "Unexpected physical source delta"):
                audit.binding()

    def test_snapshot_root_and_generator_rejected(self):
        with self.changed_json("source-snapshot.json", lambda record: record.update(Root=str(audit.BASE))):
            with self.assertRaisesRegex(ValueError, "source root"):
                audit.binding()
        with self.changed_json("physical-project-complete-inputs.json", lambda record: record.update(generator_sha256="0" * 64)):
            with self.assertRaisesRegex(ValueError, "Stage generator changed"):
                audit.binding()

    def test_short_command_inventory_and_completion_rejected(self):
        changes = (
            lambda record: record.update(passed=False),
            lambda record: record["compile_command"].append("-GBAUD=99"),
            lambda record: record["source_hashes"].pop("rtl/rv32_uart.sv"),
            lambda record: record["outputs"].pop("objects/Vrv32_soc"),
            lambda record: record.update(parent_manifest_sha256="0" * 64),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json("manifest.json", change):
                with self.assertRaises(ValueError):
                    audit.binding()

    def mapping_inputs(self):
        stage = audit.ROOT / "build/ila/relation-reuse1-seed1-native-alias"
        return tuple((stage / name).read_text(encoding="utf-8-sig")
                     for name in ("netlist.v", "cpu-remapped.fic", "verify-remapped.stdout.txt"))

    def test_actual_native_mapping_complete(self):
        netlist, fic, output = self.mapping_inputs()
        fic, output, aliases = audit.normalize_candidate_mapping(netlist, fic, output)
        result = audit.validate_config(fic, output)
        self.assertEqual((result["data_channels"], result["trigger_channels"], result["depth"]), (42, 33, 1024))
        self.assertEqual(aliases, {"board/soc/core/pipeline_valid[3]": "board/soc/unused_pipeline_valid[3]"})

    def test_missing_actual_native_channel_rejected(self):
        netlist, fic, output = self.mapping_inputs()
        rows = output.splitlines()
        self.assertEqual(sum(row.startswith("Data Channel 35:") for row in rows), 1)
        output = "\n".join(row for row in rows if not row.startswith("Data Channel 35:"))
        fic, output, _ = audit.normalize_candidate_mapping(netlist, fic, output)
        with self.assertRaisesRegex(ValueError, "Actual Inserter Data map mismatch"):
            audit.validate_config(fic, output)

    def test_wrong_pipeline_register_driver_rejected(self):
        netlist, fic, output = self.mapping_inputs()
        for index, name in ((1, "id_valid"), (3, "mem_valid")):
            before = ".Q (pipeline_valid[" + str(index) + "])"
            self.assertEqual(netlist.count(before), 1)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Wrong pipeline register driver: " + name):
                audit.normalize_candidate_mapping(netlist.replace(before, ".Q (pipeline_valid[2])"), fic, output)

    def test_wrong_mem_alias_connection_rejected(self):
        netlist, fic, output = self.mapping_inputs()
        before = r".pipeline_valid ({\core_pipeline_valid[4]_floating , unused_pipeline_valid[3],"
        self.assertEqual(netlist.count(before), 1)
        with self.assertRaisesRegex(ValueError, "Wrong MEM-valid alias connection"):
            audit.normalize_candidate_mapping(netlist.replace(before, before.replace("unused_pipeline_valid[3]", "unused_pipeline_valid[2]")), fic, output)

    def test_missing_native_fic_channel_rejected(self):
        netlist, fic, output = self.mapping_inputs()
        with self.assertRaisesRegex(ValueError, "Missing native MEM-valid channel"):
            audit.normalize_candidate_mapping(netlist, fic.replace("dataChannel<35>", "dataChannel<99>"), output)

    def test_firmware_binding_rejected(self):
        with self.changed_json("physical-project-complete-inputs.json", lambda record: record.update(parent_firmware_sha256="0" * 64)):
            with self.assertRaisesRegex(ValueError, "Wrong physical firmware"):
                audit.binding()


if __name__ == "__main__":
    unittest.main(verbosity=2)
