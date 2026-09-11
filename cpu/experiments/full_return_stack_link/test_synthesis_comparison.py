import unittest
from compare_synthesis import hierarchy


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
