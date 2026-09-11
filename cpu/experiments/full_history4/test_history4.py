import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
from test_btb_history_width import vectors




def fourth_bit_vectors():
    pattern = [0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1]
    windows = {tuple((pattern * 2)[offset:offset + 4]) for offset in range(16)}
    if len(windows) != 16:
        raise ValueError("Directed sequence does not exercise all four-bit histories")
    rows = ["0 0 100 0 100 180 0 1 0 0 104"]
    counters = None
    history = 0
    for taken in pattern * 32:
        if counters is None:
            counters = [2 if taken else 1] * 16
            history = taken
        else:
            counters[history] = min(3, counters[history] + 1) if taken else max(0, counters[history] - 1)
            history = ((history << 1) | taken) & 15
        predicted = int(counters[history] >= 2)
        values = (1, 0, 0x100, 1, 0x100, 0x180, taken, 1, 1, predicted, 0x180)
        rows.append(" ".join(f"{value:x}" for value in values))
    return rows


class HistoryFourTests(unittest.TestCase):
    def simulate(self, index_bits, address_bits, hashed, mutant=None):
        source = (ROOT / "rtl/rv32_btb.sv").read_text(encoding="utf-8")
        self.assertEqual(source.count("parameter integer HISTORY_BITS=4,"), 1)
        if mutant:
            before, after = mutant
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="history4-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            data = work / "vectors.txt"
            rows = vectors(index_bits, address_bits, hashed, 4, 2) + fourth_bit_vectors()
            data.write_text("\n".join(rows) + "\n", encoding="ascii")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "btb_history_width_tb",
                       f"-Pbtb_history_width_tb.INDEX_BITS={index_bits}",
                       f"-Pbtb_history_width_tb.ADDRESS_BITS={address_bits}",
                       f"-Pbtb_history_width_tb.HASH_INDEX={hashed}",
                       "-Pbtb_history_width_tb.HISTORY_BITS=4", "-Pbtb_history_width_tb.COUNTER_BITS=2",
                       "-o", str(image), str(rtl), str(ROOT.parents[1] / "sim/btb_history_width_tb.sv")]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], capture_output=True, text=True, timeout=30)
            return result, len(rows)

    def test_four_bit_history_geometry_and_address_boundaries(self):
        for index_bits in (2, 8):
            for address_bits in (16, 32):
                for hashed in (0, 1):
                    with self.subTest(index_bits=index_bits, address_bits=address_bits, hashed=hashed):
                        result, count = self.simulate(index_bits, address_bits, hashed)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("PASS", result.stdout)
                        self.assertGreaterEqual(count, 2379)

    def test_runtime_mutants_rejected(self):
        mutants = [("history[update_index]==PATTERN_INDEX", "history[update_index]!=PATTERN_INDEX"),
                   ("update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN", "update_taken ? WEAK_NOT_TAKEN : WEAK_TAKEN"),
                   ("pattern_prediction[history[fetch_index]]", "pattern_prediction[{1'b0,history[fetch_index][2:0]}]")]
        for mutant in mutants:
            with self.subTest(mutant=mutant[0]):
                result, _ = self.simulate(8, 16, 1, mutant)
                self.assertNotEqual(result.returncode, 0, "Actual RTL mutation escaped detection")


if __name__ == "__main__":
    unittest.main(verbosity=2)
