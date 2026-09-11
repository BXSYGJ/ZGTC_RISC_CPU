import unittest
from pathlib import Path

from ila_pipeline_minimal_config import CORE_PROPERTIES, DATA_NAMES, TRIGGER_NAMES, validate_config


ROOT = Path(__file__).resolve().parents[1]


class MinimalPipelineConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT / "scripts/cpu_ila_regfilefanout157500_minimal.fic.in").read_text(encoding="utf-8-sig")
        cls.actual = (ROOT / "build/ila-probe/regfilefanout157500-minimal-named/split.fic").read_text(encoding="utf-8-sig")
        cls.output = (ROOT / "build/ila-probe/regfilefanout157500-minimal-named/stdout.txt").read_text(encoding="utf-8-sig")
        validate_config(cls.actual, cls.output)

    def test_actual_named_mapping_and_line_endings(self):
        self.assertEqual(validate_config(self.template), validate_config(self.actual, self.output))
        self.assertTrue(validate_config(self.actual.replace("\n", "\r\n"), self.output.replace("\n", "\r\n"))["full_ex_pc_preserved"])
        self.assertEqual(len(DATA_NAMES), 42)
        self.assertEqual(len(TRIGGER_NAMES), 33)

    def test_every_capture_channel_is_required(self):
        for index, name in enumerate(DATA_NAMES):
            with self.subTest(channel=index):
                line = f"Project.unit<0>.dataChannel<{index}>={name}"
                self.assertEqual(self.template.count(line + "\n"), 1)
                with self.assertRaisesRegex(ValueError, "data map"):
                    validate_config(self.template.replace(line, line + "_wrong"))
        print("PASS split 42 individual capture-map rejections")

    def test_every_trigger_channel_is_required(self):
        for index, name in enumerate(TRIGGER_NAMES):
            with self.subTest(channel=index):
                line = f"Project.unit<0>.triggerChannel<0><{index}>={name}"
                with self.assertRaisesRegex(ValueError, "trigger map"):
                    validate_config(self.template.replace(line, line + "_wrong"))
        print("PASS split 33 individual trigger-map rejections")

    def test_all_properties_and_extra_channels_rejected(self):
        for name, value in CORE_PROPERTIES.items():
            line = f"Project.unit<0>.{name}={value}"
            with self.subTest(property=name):
                with self.assertRaisesRegex(ValueError, "property"):
                    validate_config(self.template.replace(line + "\n", line + "_wrong\n"))
        for line in ("Project.unit<0>.dataChannel<42>=cpu_clk", "Project.unit<0>.triggerChannel<0><33>=cpu_clk",
                     "Project.unit<0>.clockChannel=cpu_clk", "Project.unit<1>.dataChannel<0>=cpu_clk"):
            with self.assertRaises(ValueError):
                validate_config(self.template + line + "\n")
        print(f"PASS split {len(CORE_PROPERTIES)} property and four duplicate/extra-channel rejections")

    def test_actual_query_output_required(self):
        for old, new in (("Data Channel 41:", "Data Channel 42:"), ("Trigger Channel 32:", "Trigger Channel 33:"),
                         ("Clock Port channel:", "Wrong Clock Port:"), ("Data Max Depth:", "Wrong Data Max Depth:")):
            with self.subTest(change=old):
                self.assertIn(old, self.output)
                with self.assertRaises(ValueError):
                    validate_config(self.actual, self.output.replace(old, new))
        with self.assertRaisesRegex(ValueError, "error output"):
            validate_config(self.actual, self.output + "\nE: inserted error\n")
        with self.assertRaises(ValueError):
            validate_config(self.actual, self.output + self.output)
        print("PASS split six raw Inserter output rejections")

    def test_cross_process_numeric_mapping_is_rejected(self):
        wrong = (ROOT / "build/ila-probe/regfile157500-split-trigger-v2/split.fic").read_text(encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            validate_config(wrong)
        print("PASS actual cross-process numeric-index mapping rejected")


if __name__ == "__main__":
    unittest.main()
