from pathlib import Path
import random
import subprocess
import tempfile
import unittest
import sys

PROJECT = Path(__file__).resolve().parent
BASE = PROJECT.parent / "full_redirect_clock151200"
sys.path.insert(0, str(BASE / "scripts"))
from test_btb_local_history import vectors as original_vectors


def vectors(index_bits, address_bits, hashed, history_bits, counter_bits, extended=True):
    history_mask = (1 << history_bits) - 1
    counter_max = (1 << counter_bits) - 1
    threshold = 1 << (counter_bits - 1)
    entries = {}
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
                            "history": taken if conditional else 0, "counters": [threshold if taken else threshold - 1] * (1 << history_bits)}
                entries[location] = previous
            else:
                previous["target"] = target
                if conditional:
                    history = previous["history"]
                    counter = previous["counters"][history]
                    previous["counters"][history] = min(counter_max, counter + 1) if taken else max(0, counter - 1)
                    previous["history"] = ((history << 1) | taken) & history_mask
        entry = entries.get(index(fetch))
        hit = fetch >> address_bits == 0 and fetch % 4 == 0 and entry is not None and entry["tag"] == fetch >> (index_bits + 2)
        predicted = hit and (not entry["conditional"] or entry["counters"][entry["history"]] >= threshold)
        destination = entry["target"] if hit else (fetch + 4) & 0xffffffff
        values = (reset, invalidate, fetch, valid, pc, target, taken, conditional, int(hit), int(predicted), destination)
        result.append(" ".join(f"{value:x}" for value in values))

    add(0x100, reset=0)
    for taken in [1] * 8 + [0] * 8 + [0, 1] * 24 + [1, 0, 0, 1] * 16:
        add(0x100, taken=taken)
    if extended:
        for taken in [0, 0, 0, 1, 0, 1, 1, 1] * 24:
            add(0x100, taken=taken)
    if extended and history_bits >= 4:
        for taken in [0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1] * 16:
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



class BtbHistoryWidthTests(unittest.TestCase):
    def simulate(self, history_bits, counter_bits, index_bits=8, address_bits=16, hashed=1, variant="positive"):
        source = (PROJECT / "rv32_btb.sv").read_text(encoding="utf-8")
        mutations = {
            "ignore_high_history_bit": ("pattern_prediction[history[fetch_index]]", "pattern_prediction[history[fetch_index] & ((1 << (HISTORY_BITS-1))-1)]"),
            "wrong_training_bank": ("history[update_index]==PATTERN_INDEX", "history[update_index]!=PATTERN_INDEX"),
            "train_all_banks": ("history[update_index]==PATTERN_INDEX", "1'b1"),
            "frozen_history": ("(history[update_index] << 1) | {{(HISTORY_BITS-1){1'b0}},update_taken}", "history[update_index]"),
            "reversed_history": ("history[update_index] << 1", "history[update_index] >> 1"),
            "missing_invalidate": ("end else if (invalidate) begin\n            valid<=0;", "end else if (invalidate) begin\n            valid<=valid;"),
            "out_of_range_training": ("(update_pc >> ADDRESS_BITS)==0 &&", ""),
            "out_of_range_target": ("(update_target >> ADDRESS_BITS)==0 &&", ""),
            "wrong_initial_bias": ("update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN", "update_taken ? WEAK_NOT_TAKEN : WEAK_TAKEN"),
            "unconditional_history": ("else if (update_conditional)\n", "else\n"),
        }
        if variant != "positive":
            before, after = mutations[variant]
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="btb-history-width-") as directory:
            work = Path(directory)
            rtl = work / "rv32_btb.sv"
            rtl.write_text(source, encoding="utf-8")
            rows = vectors(index_bits, address_bits, hashed, history_bits, counter_bits)
            data = work / "vectors.txt"
            data.write_text("\n".join(rows) + "\n", encoding="ascii")
            image = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "btb_history_width_tb",
                                       f"-Pbtb_history_width_tb.INDEX_BITS={index_bits}",
                                       f"-Pbtb_history_width_tb.ADDRESS_BITS={address_bits}",
                                       f"-Pbtb_history_width_tb.HASH_INDEX={hashed}",
                                       f"-Pbtb_history_width_tb.HISTORY_BITS={history_bits}",
                                       f"-Pbtb_history_width_tb.COUNTER_BITS={counter_bits}",
                                       "-o", str(image), str(rtl), str(BASE / "sim/btb_history_width_tb.sv")],
                                      text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], text=True, capture_output=True, timeout=30)
            return result, len(rows)

    def test_reference_compatibility(self):
        for index_bits in (1, 4, 8):
            for address_bits in (16, 32):
                for hashed in (0, 1):
                    self.assertEqual(vectors(index_bits, address_bits, hashed, 1, 2, extended=False),
                                     original_vectors(index_bits, address_bits, hashed))

    def test_all_widths_sizes_bounds_and_hash(self):
        for history_bits in (1, 2, 3, 4):
            for counter_bits in (1, 2):
                for index_bits in (1, 4, 8):
                    for address_bits in (16, 32):
                        for hashed in (0, 1):
                            with self.subTest(history=history_bits, counter=counter_bits, index=index_bits, address=address_bits, hashed=hashed):
                                result, count = self.simulate(history_bits, counter_bits, index_bits, address_bits, hashed)
                                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                                self.assertIn(f"PASS local_history vectors={count}", result.stdout)

    def test_compiled_faults_rejected(self):
        for counter_bits in (1, 2):
            for variant in ("wrong_training_bank", "train_all_banks", "frozen_history", "reversed_history",
                            "missing_invalidate", "out_of_range_training", "out_of_range_target", "wrong_initial_bias", "ignore_high_history_bit"):
                with self.subTest(counter=counter_bits, variant=variant):
                    result, _ = self.simulate(4, counter_bits, variant=variant)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("FAIL local_history", result.stdout + result.stderr)


    def test_unconditional_history_is_observationally_irrelevant(self):
        for counter_bits in (1, 2):
            result, count = self.simulate(4, counter_bits, variant="unconditional_history")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(f"PASS local_history vectors={count}", result.stdout)


if __name__ == "__main__":
    unittest.main()
