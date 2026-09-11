import unittest
from unittest.mock import patch
import compare_execution
from compare_execution import ROOT, compare_records, verified_profile


class RetirementComparisonTests(unittest.TestCase):
    def test_improved_and_worsened_intervals_are_conserved(self):
        reference = [(10, 0x100, 0x63), (16, 0x104, 0x13), (17, 0x108, 0x73)]
        candidate = [(30, 0x100, 0x63), (34, 0x104, 0x13), (36, 0x108, 0x73)]
        result = compare_records(iter(reference), iter(candidate))
        self.assertEqual((result["records"], result["reference_cycles"], result["candidate_cycles"], result["saved_cycles"]), (3, 7, 6, 1))
        self.assertEqual(result["interval_changes"], {"improved": 1, "worsened": 1})
        self.assertEqual(result["saved_cycles_by_previous_opcode"], {"0x63": 2, "0x13": -1})
        self.assertEqual(sum(item["saved_cycles"] for item in result["transitions"]), 1)

    def test_reject_different_trace_lengths(self):
        reference = [(10, 0x100, 0x63), (16, 0x104, 0x13)]
        with self.assertRaisesRegex(ValueError, "lengths"):
            compare_records(reference, reference[:1])

    def test_reject_different_pc_or_instruction(self):
        reference = [(10, 0x100, 0x63), (16, 0x104, 0x13)]
        for replacement in ((16, 0x108, 0x13), (16, 0x104, 0x23)):
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, "sequence"):
                compare_records(reference, [reference[0], replacement])

    def test_reject_missing_boundaries(self):
        for records in ([], [(10, 0x100, 0x63)]):
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, "boundaries"):
                compare_records(records, records)

    def test_reject_changed_profile_artifacts_and_sources(self):
        original_hash = compare_execution.file_hash
        directory = ROOT / "build/execution-profile-current"
        targets = (directory / "uart.log.retire.bin", directory / "uart.log.retire.json",
                   directory / "objects/Vrv32_soc", directory / "firmware.hex",
                   ROOT / "profile_execution.py", ROOT / "rtl/rv32_core.sv")
        for target in targets:
            def changed_hash(filename):
                return "0" * 64 if filename == target else original_hash(filename)
            with self.subTest(target=str(target)), patch.object(compare_execution, "file_hash", changed_hash):
                with self.assertRaises(ValueError):
                    verified_profile(ROOT, "20260910-233631-e15b5716")

    def test_reject_non_increasing_cycles(self):
        reference = [(10, 0x100, 0x63), (16, 0x104, 0x13)]
        for final_cycle in (9, 10):
            with self.subTest(final_cycle=final_cycle), self.assertRaisesRegex(ValueError, "Non-increasing"):
                compare_records(reference, [(10, 0x100, 0x63), (final_cycle, 0x104, 0x13)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
