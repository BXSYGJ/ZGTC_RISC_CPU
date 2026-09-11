from pathlib import Path
import random
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


def vectors(index_bits, address_bits, hashed, history_bits, counter_bits, extended=True):
    history_mask = (1 << history_bits) - 1
    counter_max = (1 << counter_bits) - 1
    threshold = 1 << (counter_bits - 1)
    entries = {}
    pattern_bits = min(history_bits, 3)
    table = (0, 1, 2, 3, 4, 5, 6, 7, 4, 5, 6, 7, 0, 1, 2, 3)

    def pattern_index(history):
        return table[history] if history_bits == 4 else history

    mask = (1 << index_bits) - 1
    rotation = 4 % index_bits
    random_source = random.Random(104729)
    result = []

    def index(pc):
        upper = (pc >> (index_bits + 2)) & mask
        folded = ((upper << rotation) | (upper >> (index_bits - rotation))) & mask
        return ((pc >> 2) ^ (folded if hashed else 0)) & mask

    def add(fetch, pc=0x100, target=0x180, taken=1, conditional=1, valid=1, reset=1, invalidate=0):
        if not reset or invalidate:
            entries.clear()
        elif valid and pc >> address_bits == 0 and target >> address_bits == 0 and pc % 4 == 0 and target % 4 == 0:
            location = index(pc)
            tag = pc >> (index_bits + 2)
            previous = entries.get(location)
            if previous is None or previous["tag"] != tag or previous["conditional"] != conditional:
                previous = {"tag": tag, "conditional": conditional, "target": target,
                            "history": taken if conditional else 0, "counters": [threshold if taken else threshold - 1] * (1 << pattern_bits)}
                entries[location] = previous
            else:
                previous["target"] = target
                if conditional:
                    history = previous["history"]
                    counter = previous["counters"][pattern_index(history)]
                    previous["counters"][pattern_index(history)] = min(counter_max, counter + 1) if taken else max(0, counter - 1)
                    previous["history"] = ((history << 1) | taken) & history_mask
        entry = entries.get(index(fetch))
        hit = fetch >> address_bits == 0 and fetch % 4 == 0 and entry is not None and entry["tag"] == fetch >> (index_bits + 2)
        predicted = hit and (not entry["conditional"] or entry["counters"][pattern_index(entry["history"])] >= threshold)
        destination = entry["target"] if hit else (fetch + 4) & 0xffffffff
        values = (reset, invalidate, fetch, valid, pc, target, taken, conditional, int(hit), int(predicted), destination)
        result.append(" ".join(f"{value:x}" for value in values))

    add(0x100, reset=0)
    for taken in [1] * 8 + [0] * 8 + [0, 1] * 24 + [1, 0, 0, 1] * 16:
        add(0x100, taken=taken)
    if extended:
        for taken in [0, 0, 0, 1, 0, 1, 1, 1] * 24:
            add(0x100, taken=taken)
    if history_bits == 4:
        for taken in [0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1] * 32:
            add(0x100, taken=taken)
    add(0x100, conditional=0)
    add(0x100, conditional=1, taken=0)
    add(0x100, invalidate=1)
    add(0x100, taken=1)
    add(0x100, pc=0x101)
    add(0x100, target=0x181)
    if address_bits == 16:
        add(0x100, pc=0x10100, taken=0)
        add(index(0x10100) << 2, valid=0)
        add(0x100, target=0x10280 if extended else 0x10180, taken=0)
        add(0x10100, valid=0)
    for fetch in (0x101, 0x102, 0x103, 0xfffffffc):
        add(fetch, valid=0)
    pool = [0x100 + offset * 4 for offset in range(32)] + [0x500 + offset * 4 for offset in range(32)]
    for trial in range(2048):
        pc = random_source.choice(pool)
        target = random_source.choice(pool)
        fetch = pc if trial % 2 else random_source.choice(pool)
        add(fetch, pc=pc, target=target, taken=random_source.randrange(2), conditional=random_source.randrange(2),
            valid=int(trial % 7 != 0), reset=int(trial % 127 != 0), invalidate=int(trial % 113 == 0))
    return result


class FoldedHistoryTests(unittest.TestCase):
    def simulate(self, history_bits=4, index_bits=8, address_bits=16, hashed=1, mutant=None):
        source = (ROOT / "rtl/rv32_btb.sv").read_text(encoding="utf-8")
        self.assertEqual(source.count("parameter integer HISTORY_BITS=4,"), 1)
        if mutant:
            before, after = mutant
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="folded-history-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            rows = vectors(index_bits, address_bits, hashed, history_bits, 2)
            data = work / "vectors.txt"
            data.write_text("\n".join(rows) + "\n", encoding="ascii")
            image = work / "test.vvp"
            command = ["iverilog", "-g2012", "-s", "btb_history_width_tb",
                       f"-Pbtb_history_width_tb.INDEX_BITS={index_bits}",
                       f"-Pbtb_history_width_tb.ADDRESS_BITS={address_bits}",
                       f"-Pbtb_history_width_tb.HASH_INDEX={hashed}",
                       f"-Pbtb_history_width_tb.HISTORY_BITS={history_bits}",
                       "-Pbtb_history_width_tb.COUNTER_BITS=2", "-o", str(image), str(rtl),
                       str(ROOT.parents[1] / "sim/btb_history_width_tb.sv")]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], capture_output=True, text=True, timeout=30)
            return result

    def test_folded_history_geometries(self):
        for index_bits in (2, 8):
            for address_bits in (16, 32):
                for hashed in (0, 1):
                    with self.subTest(index_bits=index_bits, address_bits=address_bits, hashed=hashed):
                        result = self.simulate(4, index_bits, address_bits, hashed)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn("PASS", result.stdout)

    def test_unfolded_history_compatibility(self):
        for history_bits in (1, 2, 3):
            with self.subTest(history_bits=history_bits):
                result = self.simulate(history_bits)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_mutants_rejected(self):
        mutants = [("^value[position]", "^1'b0"),
                   ("update_pattern==PATTERN_INDEX", "update_pattern!=PATTERN_INDEX"),
                   ("update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN", "update_taken ? WEAK_NOT_TAKEN : WEAK_TAKEN")]
        for mutant in mutants:
            with self.subTest(mutant=mutant[0]):
                result = self.simulate(mutant=mutant)
                self.assertNotEqual(result.returncode, 0, "Runtime mutant was not rejected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
