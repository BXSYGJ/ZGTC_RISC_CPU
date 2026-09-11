import unittest
from pathlib import Path
from unittest.mock import patch

import audit_fetch_inputs as inputs
import audit_fetch_regressions as regressions
import audit_fetch_shorts as shorts
import audit_fetch_ila as ila


class FetchAuditTests(unittest.TestCase):
    def changed_json(self, module, target, transform):
        original = module.load
        def load(path):
            value = original(path)
            if path.resolve() == target.resolve():
                transform(value)
            return value
        return patch.object(module, "load", side_effect=load)

    def test_actual_complete_inputs_and_evidence(self):
        self.assertEqual(len(inputs.audit_inputs()["physical_source_hashes"]), 20)
        self.assertTrue(regressions.audit_regressions()["passed"])
        pair = shorts.audit_shorts()
        self.assertEqual(sorted(run["result"]["cycles"] for run in pair["runs"]), [3000565, 3001255])
        self.assertEqual(ila.binding()["clock_hz"], 153000000)

    def test_input_inventory_and_generator_drift_rejected(self):
        changes = (
            lambda value: value["physical_source_hashes"].pop("rtl/rv32_uart.sv"),
            lambda value: value["physical_source_hashes"].update({"rtl/rv32_core.sv": "0" * 64}),
            lambda value: value["support_scripts"].pop("scripts/run_pds.ps1"),
            lambda value: value.update(generator_sha256="0" * 64),
            lambda value: value.update(configuration_sha256="0" * 64),
            lambda value: value.update(parent_source_input_sha256="0" * 64),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json(inputs, inputs.ROOT / "source-inputs.json", change):
                with self.assertRaises(ValueError):
                    inputs.audit_inputs()

    def test_functional_inputs_outputs_and_commands_rejected(self):
        changes = (
            lambda value: value.update(passed=False),
            lambda value: value["sources"].pop(next(iter(value["sources"]))),
            lambda value: value["outputs"].pop(next(iter(value["outputs"]))),
            lambda value: value["runs"][0].update(execute_exit=0),
            lambda value: value["runs"][0]["compile_command"].append("-Pfetch_commit_tb.FETCH_OVERLAP=0"),
            lambda value: value["runs"].pop(),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json(regressions, regressions.FUNCTIONAL / "manifest.json", change):
                with self.assertRaises(ValueError):
                    regressions.functional()

    def test_core_matrix_outputs_and_commands_rejected(self):
        changes = (
            lambda value: value.update(passed=False),
            lambda value: value["commands"][0].append("-Pcore_tb.PREDICTOR=0"),
            lambda value: value["source_hashes"].pop("rtl/rv32_core.sv"),
            lambda value: value["outputs"].pop("core-p0-l0-12345678.trace"),
            lambda value: value["runs"][0]["parameters"].update(LOAD_USE_BUBBLE=1),
            lambda value: value["runs"].pop(),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json(regressions, regressions.REGRESSION / "manifest.json", change):
                with self.assertRaises(ValueError):
                    regressions.regression()

    def test_short_source_command_and_result_drift_rejected(self):
        target = inputs.ROOT / "build/compiled/20260911-094801-420d3685/manifest.json"
        changes = (
            lambda value: value.update(SimulationPassed=False),
            lambda value: value["SourceSnapshot"].pop("rtl/rv32_uart.sv"),
            lambda value: value["CompileCommand"].append("-GBAUD=99"),
            lambda value: value.update(UartModelClockHz=153000000),
            lambda value: value.update(UartSha256="0" * 64),
            lambda value: value.update(ResultSha256="0" * 64),
        )
        for index, change in enumerate(changes):
            with self.subTest(index=index), self.changed_json(shorts, target, change):
                with self.assertRaises(ValueError):
                    shorts.audit_shorts()

    def test_physical_wrapper_clock_and_peripherals_rejected(self):
        original = Path.read_text
        target = ila.SOURCE / "pds_soc_top.v"
        for before, after in (("153000000", "151200000"), (".ENABLE_CACHE(1)", ".ENABLE_CACHE(0)")):
            def read(path, *args, **kwargs):
                value = original(path, *args, **kwargs)
                return value.replace(before, after) if path.resolve() == target.resolve() else value
            with self.subTest(before=before), patch.object(Path, "read_text", read):
                with self.assertRaises(ValueError):
                    ila.binding()


if __name__ == "__main__":
    unittest.main(verbosity=2)
