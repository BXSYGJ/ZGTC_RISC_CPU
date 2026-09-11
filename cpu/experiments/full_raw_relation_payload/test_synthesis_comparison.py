import unittest
from compare_synthesis import hierarchy, relation_registers, validate_enable_removal, OLD, NEW


class HierarchyTests(unittest.TestCase):
    def test_named_columns_and_nested_modules(self):
        text = "| Module Inst Name | FF | LUT CARRY | LUT |\n| + core | 20 | 3 | 40 |\n| + predictor | 10 | 2 | 15 |\n"
        self.assertEqual(hierarchy(text, "predictor"), {"LUT": 15, "FF": 10, "LUT CARRY": 2})
        self.assertEqual(hierarchy(text, "core"), {"LUT": 40, "FF": 20, "LUT CARRY": 3})

    def test_missing_or_duplicate_module_rejected(self):
        header = "| Module Inst Name | LUT | FF | LUT CARRY |\n"
        row = "| + predictor | 10 | 20 | 3 |\n"
        for text in (header, header + row + row, header + header + row):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
                hierarchy(text, "predictor")

    def test_truncated_columns_rejected(self):
        with self.assertRaisesRegex(ValueError, "column count"):
            hierarchy("| Module Inst Name | LUT | FF | LUT CARRY |\n| + predictor | 10 | 20 |\n", "predictor")


class RelationEnableTests(unittest.TestCase):
    def texts(self):
        return [(directory / "synthesize/pds_soc_top_syn.vm").read_text(encoding="utf-8-sig") for directory in (OLD, NEW)]

    def test_actual_three_enable_removals(self):
        before, after = self.texts()
        self.assertEqual(validate_enable_removal(before, after)["removed_clock_enables"], 3)

    def test_unchanged_design_is_not_removal(self):
        before, _ = self.texts()
        with self.assertRaisesRegex(ValueError, "primitive transformation"):
            validate_enable_removal(before, before)

    def test_missing_and_duplicate_register_rejected(self):
        _, after = self.texts()
        with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
            relation_registers(after.replace("raw_pair_relation[0]", "unrelated[0]"))
        with self.assertRaisesRegex(ValueError, "Missing or duplicate"):
            relation_registers(after + after)

    def test_changed_clock_rejected(self):
        before, after = self.texts()
        marker = "\\raw_pair_relation[0]  ("
        start = after.index(marker)
        end = after.index(");", start)
        block = after[start:end]
        self.assertEqual(block.count(".CLK (clk)"), 1)
        modified = after[:start] + block.replace(".CLK (clk)", ".CLK (wrong_clk)") + after[end:]
        with self.assertRaisesRegex(ValueError, "clock/reset/output changed"):
            validate_enable_removal(before, modified)


if __name__ == "__main__":
    unittest.main(verbosity=2)
