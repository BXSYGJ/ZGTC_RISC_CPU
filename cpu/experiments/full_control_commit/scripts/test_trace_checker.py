import argparse
import unittest
from pathlib import Path

from check_trace import Reference


class TraceCheckerTests(unittest.TestCase):
    image = b""
    lines = []
    memory_bytes = 16384

    def replay(self, lines):
        reference = Reference(self.image, memory_bytes=self.memory_bytes)
        for line in lines:
            event, *fields = line.split()
            if event == "R":
                reference.retire(fields)
            else:
                reference.trap(fields)
        return reference

    def test_valid_trace(self):
        reference = self.replay(self.lines)
        self.assertTrue(reference.success)
        self.assertEqual(reference.traps, 13)

    def test_wrong_pc_rejected(self):
        lines = self.lines.copy()
        fields = lines[0].split()
        fields[1] = f"{int(fields[1], 16) + 4:08x}"
        lines[0] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.replay(lines)

    def test_wrong_result_rejected(self):
        lines = self.lines.copy()
        index = next(index for index, line in enumerate(lines) if line.startswith("R ") and line.split()[3] == "1")
        fields = lines[index].split()
        fields[5] = f"{int(fields[5], 16) ^ 1:08x}"
        lines[index] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.replay(lines)

    def test_wrong_instruction_rejected(self):
        lines = self.lines.copy()
        fields = lines[0].split()
        fields[2] = f"{int(fields[2], 16) ^ 128:08x}"
        lines[0] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.replay(lines)

    def test_missing_trap_rejected(self):
        lines = self.lines.copy()
        index = next(index for index, line in enumerate(lines) if line.startswith("T "))
        del lines[index]
        with self.assertRaises(AssertionError):
            self.replay(lines)

    def test_wrong_trap_value_rejected(self):
        lines = self.lines.copy()
        index = next(index for index, line in enumerate(lines) if line.startswith("T "))
        fields = lines[index].split()
        fields[3] = f"{int(fields[3], 16) ^ 1:08x}"
        lines[index] = " ".join(fields)
        with self.assertRaises(AssertionError):
            self.replay(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--memory-bytes", type=int, choices=(16384, 32768), default=16384)
    args = parser.parse_args()
    TraceCheckerTests.image = args.image.read_bytes()
    TraceCheckerTests.memory_bytes = args.memory_bytes
    TraceCheckerTests.lines = args.trace.read_text(encoding="ascii").splitlines()
    unittest.main(argv=["test_trace_checker.py"])
