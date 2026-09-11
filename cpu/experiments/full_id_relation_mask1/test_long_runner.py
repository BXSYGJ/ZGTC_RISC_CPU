import copy
import unittest
from unittest.mock import patch

import run_long as runner


class LongGateTests(unittest.TestCase):
    def test_current_physical_image(self):
        evidence = runner.physical_gate()
        self.assertEqual(evidence["post_route_luts"], 9632)
        self.assertGreaterEqual(evidence["setup_wns_ns"], 0)

    def changed_record(self, change):
        original = runner.load_json
        def read(path):
            record = original(path)
            if path.name == "physical-qualification.json":
                change(record)
            return record
        return patch.object(runner, "load_json", side_effect=read)

    def test_failed_timing_rejected(self):
        with self.changed_record(lambda record: record.update(physical_timing_passed=False)):
            with self.assertRaisesRegex(ValueError, "timing gate failed"):
                runner.physical_gate()

    def test_fabricated_resource_count_rejected(self):
        with self.changed_record(lambda record: record["resources"].update(post_route_luts=1)):
            with self.assertRaisesRegex(ValueError, "Raw physical reports differ"):
                runner.physical_gate()

    def test_missing_output_rejected(self):
        with self.changed_record(lambda record: record["outputs_sha256"].pop("bitstream")):
            with self.assertRaisesRegex(ValueError, "Incomplete full-image outputs"):
                runner.physical_gate()

    def test_incomplete_ila_rejected(self):
        with self.changed_record(lambda record: record["ila"].update(data_channels=41)):
            with self.assertRaisesRegex(ValueError, "Incomplete ILA configuration"):
                runner.physical_gate()

    def test_actual_long_references(self):
        physical = runner.physical_gate()
        for validation in (False, True):
            original = runner.BASE / "build/compiled" / runner.SOURCES[int(validation)]
            manifest = runner.load_json(original / "manifest.json")
            result = runner.load_json(original / "result.json")
            runner.validate_reference(manifest, result, validation, physical)

    def test_short_wrong_seed_and_model_clocks_rejected(self):
        original = runner.BASE / "build/compiled" / runner.SOURCES[0]
        manifest = runner.load_json(original / "manifest.json")
        result = runner.load_json(original / "result.json")
        physical = runner.physical_gate()
        for field, value in (("iterations", 10), ("clock_hz", 157500000), ("validation_run", True), ("modeled_duration_at_least_10s", False)):
            changed = dict(result, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner.validate_reference(manifest, changed, False, physical)
        changed = copy.deepcopy(manifest)
        changed["SimulationClockHz"] = 151200000
        with self.assertRaisesRegex(ValueError, "model clocks differ"):
            runner.validate_reference(changed, result, False, physical)


if __name__ == "__main__":
    unittest.main(verbosity=2)
