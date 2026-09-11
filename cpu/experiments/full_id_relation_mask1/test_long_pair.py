import copy
import unittest
from unittest.mock import patch

import audit_long_pair as auditor


class LongPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prerequisite = auditor.runner.physical_gate()
        cls.physical = [auditor.read_physical(validation) for validation in (False, True)]

    def test_current_pair_and_resource_rejection(self):
        for validation in (False, True):
            result = auditor.read_run(validation, self.physical[int(validation)], self.prerequisite)
            self.assertEqual(result["result"]["iterations"], 6000)
            self.assertEqual(result["result"]["cycles"], (1795360650, 1795883504)[int(validation)])
        report = auditor.audit()
        self.assertTrue(report["local_pair_validated"])
        self.assertTrue(report["coremark_floor_passed"])
        self.assertFalse(report["resource_floor_passed"])
        self.assertFalse(report["local_metric_gates_passed"])
        self.assertFalse(report["hardware_validated"])
        self.assertFalse(report["baseline_replaced"])
        self.assertEqual(report["maximum_luts_at_measured_score"], 9453)
        self.assertEqual(report["minimum_lut_reduction_at_unchanged_score"], 179)

    def changed_manifest(self, change, validation=False):
        original = auditor.load_json
        directory = auditor.ROOT / "build" / ("long-v1" if validation else "long-v0")
        def read(path):
            result = original(path)
            if path == directory / "manifest.json":
                change(result)
            return result
        return patch.object(auditor, "load_json", side_effect=read)

    def test_incomplete_seed_clock_and_runner_rejected(self):
        changes = (
            lambda record: record.update(passed=False),
            lambda record: record.update(validation_run=True),
            lambda record: record.update(simulation_clock_hz=151200000),
            lambda record: record.update(uart_model_clock_hz=115200),
            lambda record: record.update(max_cycles=5000000000),
            lambda record: record.update(runner_sha256="0" * 64),
            lambda record: record.update(base_manifest_sha256="0" * 64),
            lambda record: record.update(base_build="/mnt/d/unrelated"),
            lambda record: record["physical_prerequisite"].update(post_route_luts=1),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_manifest(change), self.assertRaises(ValueError):
                auditor.read_run(False, self.physical[0], self.prerequisite)

    def test_missing_or_changed_sources_rejected(self):
        changes = (
            lambda record: record["source_hashes"].pop("rtl/rv32_uart.sv"),
            lambda record: record["source_hashes"].update({"rtl/rv32_core.sv": "0" * 64}),
            lambda record: record["source_hashes"].update({"sim/coremark_compiled.cpp": "0" * 64}),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_manifest(change), self.assertRaises(ValueError):
                auditor.read_run(False, self.physical[0], self.prerequisite)

    def test_compiler_and_hardware_substitutions_rejected(self):
        changes = (
            lambda record: record["compile_command"].append("-GBAUD=200"),
            lambda record: record["hardware_parameters"].update(ENABLE_CACHE=0),
            lambda record: record["firmware_build"].update(Iterations=10),
            lambda record: record.update(firmware_sha256="0" * 64),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_manifest(change), self.assertRaises(ValueError):
                auditor.read_run(False, self.physical[0], self.prerequisite)

    def test_every_output_hash_and_inventory_enforced(self):
        for name in sorted(auditor.OUTPUTS):
            with self.subTest(name=name):
                with self.changed_manifest(lambda record: record["outputs"].pop(name)):
                    with self.assertRaisesRegex(ValueError, "Incomplete long output"):
                        auditor.read_run(False, self.physical[0], self.prerequisite)
                with self.changed_manifest(lambda record: record["outputs"].update({name: "0" * 64})):
                    with self.assertRaisesRegex(ValueError, "Long output changed"):
                        auditor.read_run(False, self.physical[0], self.prerequisite)

    def test_v1_requires_its_own_firmware(self):
        with self.assertRaisesRegex(ValueError, "firmware differs from its physical image"):
            auditor.read_run(True, self.physical[0], self.prerequisite)

    def test_physical_source_mismatch_rejected(self):
        physical = copy.deepcopy(self.physical[0])
        physical["source_binding"]["physical_source_hashes"]["rtl/rv32_core.sv"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Physical and simulated RTL differ"):
            auditor.read_run(False, physical, self.prerequisite)

    def test_stored_result_reparsed(self):
        original = auditor.load_json
        target = auditor.ROOT / "build/long-v0/result.json"
        def changed(path):
            record = original(path)
            if path == target:
                record["cycles_saved"] += 1
            return record
        with patch.object(auditor, "load_json", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Stored result differs from parsed UART"):
                auditor.read_run(False, self.physical[0], self.prerequisite)

    def test_exact_lut_boundary_and_no_rounding(self):
        result = {"iterations": 6000, "cycles": 1795360650, "clock_hz": 151200000}
        self.assertTrue(auditor.evaluate(result, 9453)["resource_floor_passed"])
        self.assertFalse(auditor.evaluate(result, 9454)["resource_floor_passed"])
        for value in (0, -1, 9370.0, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                auditor.evaluate(result, value)
        result["cycles"] = 6000000000
        self.assertFalse(auditor.evaluate(result, 100)["coremark_floor_passed"])

    def test_portable_paths(self):
        self.assertEqual(auditor.portable("D:" + chr(92) + "AAAFPGA"), "/mnt/d/AAAFPGA")
        self.assertEqual(auditor.portable("D:/AAAFPGA/"), "/mnt/d/AAAFPGA")
        self.assertEqual(auditor.portable("/mnt/d/AAAFPGA"), "/mnt/d/AAAFPGA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
