
from pathlib import Path
import tempfile
import unittest

from compare_coremark import read_case
from run_coremark_compiled import (BINARY_PARAMETERS, check_simulation_result, configuration_word,
                                   file_hash, hardware_parameters, validate_compiler_warnings,
                                   validate_configuration_binding, validate_firmware, verify_artifacts)
from test_coremark_checker import fixture


def configuration():
    result = {field: 1 for field in BINARY_PARAMETERS}
    result.update(LoadUseBubble=0, CacheSetBits=6, ICacheSetBits=8, BtbIndexBits=8)
    return result


class CompiledSimulationTests(unittest.TestCase):
    def test_hardware_field_types_and_geometry(self):
        valid = configuration()
        self.assertEqual(configuration_word(hardware_parameters(valid)), 0x0e8e86f9)
        for field in BINARY_PARAMETERS:
            for invalid in (True, "1", -1, 2):
                changed = {**valid, field: invalid}
                with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(ValueError, "binary hardware"):
                    hardware_parameters(changed)
        for field in ("CacheSetBits", "ICacheSetBits", "BtbIndexBits"):
            for invalid in (0, 9, True, "8"):
                with self.subTest(field=field, invalid=invalid), self.assertRaisesRegex(ValueError, "width hardware"):
                    hardware_parameters({**valid, field: invalid})

    def test_inherited_geometry_and_bypass(self):
        valid = configuration()
        del valid["ICacheSetBits"]
        self.assertEqual(configuration_word(hardware_parameters(valid)), 0x0e8e06f9)
        valid["ICacheSetBits"] = 6
        self.assertEqual(configuration_word(hardware_parameters(valid)), 0x0e8e06f9)
        valid["CacheEnabled"] = 0
        encoded = configuration_word(hardware_parameters(valid))
        self.assertEqual(encoded & ((1 << 19) | 64 | 8), 0)
        self.assertEqual(encoded & 2, 2)

    def test_firmware_byte_and_metadata_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "firmware.hex"
            path.write_text("00000013\n" * 16384, encoding="ascii")
            metadata = {"HexSha256": file_hash(path), "EnableM": 1, "Iterations": 4000,
                        "ValidationRun": False, "ClockHz": 120000000}
            parameters = hardware_parameters(configuration())
            validate_firmware(path, metadata, parameters)
            for field, invalid in (("HexSha256", "0" * 64), ("EnableM", True), ("Iterations", 0),
                                   ("ValidationRun", 0), ("ClockHz", True)):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    validate_firmware(path, {**metadata, field: invalid}, parameters)
            with self.assertRaisesRegex(ValueError, "requires M-enabled"):
                validate_firmware(path, metadata, {**parameters, "ENABLE_M": 0})
            path.write_text("00000013\n" * 16383, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "16384"):
                validate_firmware(path, metadata, parameters)

    def test_simulation_result_is_not_a_hardware_score(self):
        parameters = hardware_parameters(configuration())
        metadata = {"Iterations": 120, "ValidationRun": False, "ClockHz": 27000000}
        text = fixture() + "\nZGTC config=0e8e86f9 ihit=1 imiss=2 dhit=3 dmiss=4 writebacks=5\n"
        result = check_simulation_result(text, metadata, parameters, False)
        self.assertTrue(result["modeled_duration_at_least_10s"])
        self.assertEqual(result["measurement_kind"], "rtl_simulation_not_hardware")
        self.assertNotIn("reportable_duration", result)
        self.assertFalse(any(key.startswith("iterations_per_second") for key in result))
        for field, value in (("Iterations", 1), ("ValidationRun", True)):
            with self.assertRaisesRegex(ValueError, "iteration or seed"):
                check_simulation_result(text, {**metadata, field: value}, parameters, False)
        with self.assertRaises(ValueError):
            check_simulation_result(text.replace("0e8e86f9", "0e8e06f9"), metadata, parameters, False)

    def test_compiled_uart_rejected_by_hardware_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            uart = Path(directory) / "coremark.sim.uart"
            uart.write_text("ZGTC RTL_SIMULATION_ONLY\n" + fixture(), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "simulation cannot be used as hardware"):
                read_case(Path(directory) / "missing-hardware", uart)

    def test_narrow_legacy_warning_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            memory = source / "rtl" / "rv32_burst_ram.sv"
            memory.parent.mkdir()
            memory.write_text('if(INIT_FILE!="") $readmemh(INIT_FILE,memory);\n', encoding="utf-8")
            warning = (f"%Warning-WIDTH: {memory}:1:21: Operator NEQ expects 680 bits on the RHS, "
                       "but RHS's CONST '?1?h0' generates 1 bits.")
            validate_compiler_warnings(warning, source)
            validate_compiler_warnings("", source)
            for invalid in (warning.replace(":1:21:", ":2:21:"), warning.replace("WIDTH", "UNUSED"),
                            warning.replace("NEQ", "ADD"), warning.replace("rv32_burst_ram", "rv32_cache")):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "Unapproved"):
                    validate_compiler_warnings(invalid, source)

    def test_implementation_input_binding(self):
        firmware = {"ClockHz": 120000000, "HexSha256": "A" * 64}
        sources = {"rtl/rv32_core.sv": "B" * 64, "sim/coremark_compiled.cpp": "C" * 64}
        configuration_input = {"ClockHz": 120000000, "FirmwareSha256": "a" * 64,
                               "SourceSnapshot": {"Schema": 1, "Files": {"rtl/rv32_core.sv": "b" * 64}}}
        self.assertTrue(validate_configuration_binding(configuration_input, firmware, sources))
        self.assertFalse(validate_configuration_binding({}, firmware, sources))
        for field, value in (("ClockHz", 27000000), ("FirmwareSha256", "0" * 64),
                             ("SourceSnapshot", {"Schema": 1, "Files": {}}),
                             ("SourceSnapshot", {"Schema": 2, "Files": {}})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_configuration_binding({**configuration_input, field: value}, firmware, sources)

    def test_snapshot_and_executable_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            paths = {"source": build / "source" / "rtl" / "core.sv",
                     "firmware": build / "firmware.hex", "executable": build / "objects" / "Vrv32_soc"}
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original")
            manifest = {"SourceSnapshot": {"rtl/core.sv": file_hash(paths["source"])},
                        "FirmwareSha256": file_hash(paths["firmware"]),
                        "ExecutableSha256": file_hash(paths["executable"])}
            verify_artifacts(build, manifest)
            for kind, path in paths.items():
                path.write_bytes(b"changed")
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "changed"):
                    verify_artifacts(build, manifest)
                path.write_bytes(b"original")


if __name__ == "__main__":
    unittest.main()
