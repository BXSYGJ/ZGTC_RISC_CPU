"""Synthetic-only controls for ownership and incomplete/duplicate export rejection."""
import tempfile
from pathlib import Path
import unittest

from inspect_native_export import inspect


def cell(kind, owner, name, ports, parameters=""):
    annotation = " /* " + owner + " */" if owner else ""
    parameter_block = " #(" + parameters + ")" if parameters else ""
    connections = ",".join("." + name + " (" + value + ")" for name, value in ports.items())
    return "    " + kind + annotation + parameter_block + "\n        " + chr(92) + name + "  (" + connections + ");\n"


class SyntheticExportControls(unittest.TestCase):
    def inspect_text(self, text):
        with tempfile.TemporaryDirectory(prefix="synthetic-native-export-") as directory:
            path = Path(directory) / "synthetic.v"
            path.write_text("module synthetic;\n" + text + "endmodule\n", encoding="utf-8")
            return inspect(path)

    def ground(self):
        return cell("V_LUT6CARRY", "GND_1/FYA/LUT6CARRY", "CLMA_1_1/FYA/LUT6CARRY",
                    {"Z": "_GND1", "Z5": "", "COUT": "", "I0": ""}, ".INIT(64'b" + "0" * 64 + ")")

    def test_shared_constant_crosses_unowned_buffer(self):
        text = self.ground()
        text += cell("V_BUF", "", "CLMA_1_1/buf", {"I": "_GND1", "Z": "buffered_zero"})
        text += cell("V_FFASYN", "core_boundary/dut/machine/counter[63]/FF0/FF", "CLMA_2_1/FF0/FF",
                     {"D": "buffered_zero", "Q": "core_q"})
        text += cell("V_FFASYN", "active_inputs[5]/FF0/FF", "CLMA_3_1/FF0/FF",
                     {"D": "buffered_zero", "Q": "fixture_q"})
        report = self.inspect_text(text)
        self.assertEqual(report["summary"]["constant_site_consumer_categories"], {"shared": 1})
        self.assertEqual(report["constant_site_consumer_traces"][0]["reached_regions"], ["core", "fixture"])

    def test_dangling_constant_remains_unowned(self):
        report = self.inspect_text(self.ground())
        self.assertEqual(report["summary"]["constant_site_consumer_categories"], {"no_owned_consumer": 1})

    def test_physical_lut_ram_slot_overlap_is_rejected(self):
        text = self.ground() + cell("V_RAM64X1", "core_boundary/dut/memory/FYA/RAM64", "CLMA_1_1/FYA/RAM64",
                                   {"RDO": "ram_q", "WDI": "ram_d"})
        with self.assertRaisesRegex(ValueError, "same exported physical slot"):
            self.inspect_text(text)

    def test_unknown_primitive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unrecognized physical primitive"):
            self.inspect_text(cell("V_UNKNOWN", "", "CLMA_1_1/UNKNOWN", {"I": "x", "Z": "y"}))

    def test_false_ground_annotation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "matching actual LUT INIT"):
            self.inspect_text(self.ground().replace("64'b" + "0" * 64, "64'b" + "1" * 64))


if __name__ == "__main__":
    unittest.main(verbosity=2)
