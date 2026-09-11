import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analyze_branch_history import HEADER, LocalResolutionReplay, ResolutionReplay, analyze, decoded_target, folded_index


def branch_instruction(offset, function=0):
    immediate = offset & 8191
    return (((immediate >> 12) & 1) << 31) | (((immediate >> 5) & 63) << 25) | (2 << 20) | (1 << 15) | (function << 12) | (((immediate >> 1) & 15) << 8) | (((immediate >> 11) & 1) << 7) | 99


def row(cycle, window, pc, target, taken, predicted):
    instruction = branch_instruction(target - pc)
    actual = target if taken else pc + 4
    return f"{cycle},{window},{pc:08x},{instruction:08x},{target:08x},{actual:08x},{predicted:08x},{taken},1"


def fixture():
    return "\n".join(["schema,1,start_pc,00001398,stop_pc,00005a88,sampling,post_negative_edge", ",".join(HEADER),
                      row(1, 0, 0x100, 0x108, 1, 0x104), row(2, 1, 0x108, 0x100, 1, 0x10c),
                      row(3, 1, 0x100, 0x108, 0, 0x108), row(4, 0, 0x108, 0x100, 1, 0x100),
                      "END,4,5,3", ""])


class BranchHistoryTests(unittest.TestCase):
    def test_observed_counts_and_warmup(self):
        report = analyze(fixture())
        self.assertEqual(report["total_records"], 4)
        self.assertEqual(report["observed"]["branch_resolutions"], 2)
        self.assertEqual(report["observed"]["branch_redirects"], 2)
        self.assertEqual(report["observed"]["branch_direction_redirects"], 2)
        self.assertEqual(report["replay"]["0"]["prediction_differs_from_observed"], 0)
        self.assertEqual(set(report["replay"]), {"0", "1", "2", "4", "6", "8", "local_1", "local_2", "local_3"})
        self.assertIn("omits in-flight", report["replay_scope"])

    def test_decoder_signed_offsets_and_jumps(self):
        for offset in (-4096, -8, 0, 8, 4094):
            for function in (0, 1, 4, 5, 6, 7):
                self.assertEqual(decoded_target(0x2000, branch_instruction(offset, function)), 0x2000 + offset)
        self.assertEqual(decoded_target(0x100, 0x0080006f), 0x108)
        self.assertIsNone(decoded_target(0x100, 0x00008067))
        for instruction in (0, branch_instruction(8, 2), branch_instruction(8, 3), 0x00001067):
            with self.assertRaises(ValueError):
                decoded_target(0x100, instruction)

    def test_trace_corruptions_rejected(self):
        original = fixture()
        changes = [("schema,1", "schema,2"), ("END,4,5,3", "END,3,5,3"),
                   ("END,4,5,3", "END,4,2,3"), ("END,4,5,3\n", ""),
                   ("2,1,", "1,1,"), ("2,1,", "2,2,"),
                   ("00000108,fe208ce3,00000100", "00000108,fe208ce3,00000104"),
                   ("00000100,00208463,00000108,00000104", "00000100,00208463,00000108,00000108")]
        for before, after in changes:
            with self.subTest(before=before):
                self.assertIn(before, original)
                with self.assertRaises(ValueError):
                    analyze(original.replace(before, after, 1))
        with self.assertRaises(ValueError):
            analyze(original + row(5, 0, 0x100, 0x108, 0, 0x104) + "\n")
        with self.assertRaises(ValueError):
            analyze(original.replace("4,0,", "4,1,").replace("3,1,", "3,0,"))

    def test_bimodal_saturation_replacement_and_class(self):
        model = ResolutionReplay(0)
        self.assertEqual(model.step(0x100, 0x108, 1, 1), 0x104)
        for _ in range(8):
            self.assertEqual(model.step(0x100, 0x108, 1, 1), 0x108)
        self.assertEqual(model.counters[folded_index(0x100)], 3)
        for _ in range(8):
            model.step(0x100, 0x108, 0, 1)
        self.assertEqual(model.counters[folded_index(0x100)], 0)
        self.assertEqual(folded_index(0x100), folded_index(0x540))
        self.assertEqual(model.step(0x540, 0x550, 1, 0), 0x544)
        self.assertEqual(model.step(0x540, 0x550, 1, 0), 0x550)
        self.assertEqual(model.step(0x100, 0x108, 0, 1), 0x104)

    def test_global_history_conditional_only(self):
        model = ResolutionReplay(2)
        model.step(0x100, 0x108, 1, 1)
        self.assertEqual(model.history, 1)
        model.step(0x104, 0x200, 1, 0)
        self.assertEqual(model.history, 1)
        model.step(0x100, 0x108, 0, 1)
        self.assertEqual(model.history, 2)
        for invalid in (-1, 9, True):
            with self.assertRaises(ValueError):
                ResolutionReplay(invalid)

    def test_local_alternation_and_reallocation(self):
        model = LocalResolutionReplay(1)
        predictions = []
        for trial in range(20):
            taken = trial % 2
            predictions.append(model.step(0x100, 0x108, taken, 1))
        self.assertEqual(predictions[-4:], [0x104, 0x108, 0x104, 0x108])
        index = folded_index(0x100)
        self.assertEqual(model.counters[index], [3, 0])
        model.step(0x540, 0x550, 0, 1)
        self.assertEqual(model.counters[index], [1, 1])
        self.assertEqual(model.history[index], 0)
        for invalid in (0, 4, True):
            with self.assertRaises(ValueError):
                LocalResolutionReplay(invalid)

    def test_cli_refuses_overwriting_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.csv"
            output = Path(directory) / "report.json"
            trace.write_text(fixture(), encoding="ascii")
            script = Path(__file__).with_name("analyze_branch_history.py")
            command = [sys.executable, str(script), "--trace", str(trace), "--json", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            before = output.read_bytes()
            self.assertEqual(json.loads(before)["total_records"], 4)
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
