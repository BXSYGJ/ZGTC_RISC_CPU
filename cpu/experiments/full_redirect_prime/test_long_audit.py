import unittest

from audit_short import ROOT, read_run


class LongComparisonInputTests(unittest.TestCase):
    def test_existing_long_pair_accepted(self):
        for validation, build in enumerate(("20260910-200328-351ec921", "20260910-200355-357efcf4")):
            with self.subTest(validation=validation):
                directory = ROOT.parent / "full_control_commit/build/compiled" / build
                manifest, result = read_run(directory, iterations=6000)
                self.assertTrue(result["modeled_duration_at_least_10s"])
                self.assertEqual(result["validation_run"], bool(validation))
                self.assertTrue(manifest["CompletedUtc"])

    def test_short_run_rejected_as_long(self):
        directory = ROOT / "build/compiled/20260910-221841-e6c87093"
        with self.assertRaises((ValueError, RuntimeError)):
            read_run(directory, iterations=6000)

    def test_unsupported_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported comparison duration"):
            read_run(ROOT / "build/compiled/not-created", iterations=100)


if __name__ == "__main__":
    unittest.main(verbosity=2)

