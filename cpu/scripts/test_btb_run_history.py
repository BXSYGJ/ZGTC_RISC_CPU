from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from load_use_profile import file_hash
from test_btb_history_width import vectors as shift_vectors


PROJECT = Path(__file__).resolve().parents[1]


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
                            "history": (taken << (history_bits-1)) if conditional else 0, "counters": [threshold if taken else threshold - 1] * (1 << history_bits)}
                entries[location] = previous
            else:
                previous["target"] = target
                if conditional:
                    history = previous["history"]
                    counter = previous["counters"][history]
                    previous["counters"][history] = min(counter_max, counter + 1) if taken else max(0, counter - 1)
                    direction = history >> (history_bits-1)
                    run_mask = history_mask >> 1
                    count = history & run_mask
                    previous["history"] = (taken << (history_bits-1)) | (min(run_mask,count+1) if direction==taken else 0)
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



class RunHistoryTests(unittest.TestCase):
    def simulate(self, history_bits, counter_bits, index_bits=8, address_bits=16, hashed=1, variant="positive"):
        source = (PROJECT / "experiments/btb_run_history/rv32_btb.sv").read_text(encoding="utf-8")
        mutations = {
            "wrong_training_bank": ("history[update_index]==PATTERN_INDEX", "history[update_index]!=PATTERN_INDEX"),
            "train_all_banks": ("history[update_index]==PATTERN_INDEX", "1'b1"),
            "wrong_direction": ("prior_history[HISTORY_BITS-1]==update_taken", "prior_history[HISTORY_BITS-1]!=update_taken"),
            "missing_saturation": ("run_saturated ? prior_history", "1'b0 ? prior_history"),
            "frozen_history": ("history[update_index]<=next_history;", "history[update_index]<=history[update_index];"),
            "shift_history": ("history[update_index]<=next_history;", "history[update_index]<=(history[update_index] << 1) | update_taken;"),
            "missing_invalidate": ("end else if (invalidate) begin\n            valid<=0;", "end else if (invalidate) begin\n            valid<=valid;"),
            "out_of_range_training": ("(update_pc >> ADDRESS_BITS)==0 &&", ""),
            "out_of_range_target": ("(update_target >> ADDRESS_BITS)==0 &&", ""),
            "wrong_initial_bias": ("update_taken ? WEAK_TAKEN : WEAK_NOT_TAKEN", "update_taken ? WEAK_NOT_TAKEN : WEAK_TAKEN"),
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
                                       "-o", str(image), str(rtl), str(PROJECT / "sim/btb_history_width_tb.sv")],
                                      text=True, capture_output=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], text=True, capture_output=True, timeout=30)
            return result, len(rows)

    def test_canonical_and_h1_compatibility(self):
        self.assertEqual(file_hash(PROJECT / 'experiments/btb_run_history/rv32_btb.sv'),'0FF6374376C12FBD4467BA20523A2ED60E0BF1E56A97953E9CC1F4BF8E2D5DC9')
        for counter_bits in (1,2):
            for address_bits in (16,32):
                self.assertEqual(vectors(8,address_bits,1,1,counter_bits),shift_vectors(8,address_bits,1,1,counter_bits))

    def test_all_configurations(self):
        configurations = 0
        rows_total = 0
        for history_bits in (1,2,3):
            for counter_bits in (1,2):
                for index_bits in (1,4,8):
                    for address_bits in (16,32):
                        for hashed in (0,1):
                            result,rows = self.simulate(history_bits,counter_bits,index_bits,address_bits,hashed)
                            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                            self.assertIn('PASS',result.stdout)
                            configurations += 1
                            rows_total += rows
        print(f'PASS run-history RTL configurations={configurations} vectors={rows_total}')

    def test_actual_runtime_mutants(self):
        for variant in ('wrong_training_bank','train_all_banks','wrong_direction','missing_saturation','frozen_history','shift_history','missing_invalidate','out_of_range_training','out_of_range_target','wrong_initial_bias'):
            result,rows = self.simulate(3,2,variant=variant)
            self.assertNotEqual(result.returncode,0,variant)
            self.assertIn('FATAL',result.stdout+result.stderr)
            print('PASS run-history RTL rejection: '+variant)


if __name__ == '__main__':
    unittest.main(verbosity=2)
