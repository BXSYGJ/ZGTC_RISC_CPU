import unittest

import audit_fetch_ila as audit


class ScopeRoleTests(unittest.TestCase):
    source = audit.ROOT / "build/pds/20260911-105255-fc9be582"

    def test_actual_application_role_retains_complete_cpu(self):
        bound = audit.binding(self.source, scope=True)
        reference = audit.binding()
        self.assertEqual(bound["physical_source_hashes"], reference["physical_source_hashes"])
        self.assertEqual(bound["hardware_parameters"], reference["hardware_parameters"])
        self.assertEqual(bound["firmware_sha256"], "4D6AF10D6117FEC061273512E0AABF36B7916B357BFE66E152C89C6E3A388B06")
        self.assertTrue(bound["application_firmware"]["passed"])
        self.assertNotIn("application_firmware", reference)

    def test_rejects_mixed_or_invalid_roles(self):
        for validation, scope in ((True, True), (False, 1), (False, "scope"), (False, None)):
            with self.subTest(validation=validation, scope=scope), self.assertRaisesRegex(ValueError, "Invalid physical firmware role"):
                audit.binding(self.source, validation=validation, scope=scope)

    def test_scope_cannot_masquerade_as_benchmark(self):
        for validation in (False, True):
            with self.subTest(validation=validation), self.assertRaisesRegex(ValueError, "Wrong 153 MHz physical firmware"):
                audit.binding(self.source, validation=validation)
        with self.assertRaisesRegex(ValueError, "Captured scope firmware differs"):
            audit.binding(audit.SOURCE, scope=True)

    def test_both_existing_benchmark_mapping_receipts_unchanged(self):
        cases = (("fetch-commit-seed1-native-wb", audit.SOURCE, False),
                 ("fetch-commit-v1-seed1", audit.ROOT / "build/pds/20260911-101436-c57addf3", True))
        for name, source, validation in cases:
            with self.subTest(name=name):
                stage = audit.ROOT / "build/ila" / name
                checksum = audit.digest(stage / "mapping-audit.json")
                result = audit.mapping(stage, source, validation=validation)
                self.assertEqual(audit.digest(stage / "mapping-audit.json"), checksum)
                self.assertEqual((result["data_channels"], result["trigger_channels"], result["depth"]), (42, 33, 1024))


if __name__ == "__main__":
    unittest.main(verbosity=2)
