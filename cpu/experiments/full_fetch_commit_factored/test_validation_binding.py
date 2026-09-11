import unittest

import audit_fetch_ila as audit


class FirmwareRoleTests(unittest.TestCase):
    validation_source = audit.ROOT / "build/pds/20260911-101436-c57addf3"

    def test_both_current_firmware_roles(self):
        performance = audit.binding()
        validation = audit.binding(self.validation_source, validation=True)
        self.assertEqual(performance["firmware_sha256"], "6DAAE1B97ED63CBD65BFF5A8F6BD15FC4E67378BA3316D790911EF5CF5D545CD")
        self.assertEqual(validation["firmware_sha256"], "9ECD2172E0412543BB5D55E386D77549B8817F7602ACD2F0D0591F7306BD1FE5")
        self.assertEqual(performance["physical_source_hashes"], validation["physical_source_hashes"])
        self.assertEqual(performance["hardware_parameters"], validation["hardware_parameters"])

    def test_wrong_firmware_role_rejected(self):
        for source, validation in ((audit.SOURCE, True), (self.validation_source, False)):
            with self.subTest(validation=validation), self.assertRaisesRegex(ValueError, "Wrong 153 MHz physical firmware"):
                audit.binding(source, validation)

    def test_invalid_role_type_rejected(self):
        for role in (0, 1, "false", "true", None):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "Invalid physical firmware role"):
                audit.binding(validation=role)

    def test_existing_performance_mapping_is_unchanged(self):
        stage = audit.ROOT / "build/ila/fetch-commit-seed1-native-wb"
        checksum = audit.digest(stage / "mapping-audit.json")
        mapped = audit.mapping(stage)
        self.assertEqual(checksum, audit.digest(stage / "mapping-audit.json"))
        self.assertEqual((mapped["data_channels"], mapped["trigger_channels"], mapped["depth"]), (42, 33, 1024))


if __name__ == "__main__":
    unittest.main(verbosity=2)
