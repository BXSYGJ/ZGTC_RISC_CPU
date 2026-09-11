import hashlib
import json
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"


def vectors(depth):
    entries = {}
    stack = []
    output = []
    random_source = random.Random(13007)

    def index(address):
        upper = (address >> 10) & 255
        return ((address >> 2) ^ (upper << 4) ^ (upper >> 4)) & 255

    def add(fetch=0x300, pc=0x300, target=0x180, valid=0, conditional=0, taken=1,
            is_return=0, push=0, pop=0, reset=1, invalidate=0):
        if not reset or invalidate:
            entries.clear()
            stack.clear()
        else:
            if valid and pc < 65536 and target < 65536 and pc % 4 == 0 and target % 4 == 0:
                entries[index(pc)] = (pc >> 10, target, conditional, is_return)
            if depth:
                if pop and stack:
                    stack.pop()
                if push:
                    stack.append((pc + 4) & 0xffffffff)
                    if len(stack) > depth:
                        stack.pop(0)
        entry = entries.get(index(fetch))
        hit = fetch < 65536 and fetch % 4 == 0 and entry is not None and entry[0] == fetch >> 10
        destination = fetch + 4 & 0xffffffff
        if hit:
            destination = stack[-1] if depth and stack and entry[3] and not entry[2] else entry[1]
        row = (reset, invalidate, fetch, valid, pc, target, taken, conditional, is_return,
               push, pop, int(hit), destination, len(output))
        output.append(" ".join(f"{value:x}" for value in row))

    add(reset=0)
    add(valid=1, is_return=1)
    for address in (0x100, 0x140, 0x180, 0x1c0, 0x200, 0x240):
        add(pc=address, push=1)
    for _ in range(8):
        add(pop=1)
    add(pc=0x100, push=1)
    add(pc=0x140, push=1)
    add(pc=0x200, push=1, pop=1)
    add(pop=1)
    add(pc=0xfffffffc, push=1)
    add(pc=0x300, target=0x144, valid=1, is_return=0)
    add(pc=0x300, target=0x148, valid=1, is_return=1)
    add(pc=0x300, valid=1, conditional=1, is_return=1)
    add(pc=0x300, valid=1, is_return=1)
    add(invalidate=1)
    add(valid=1, is_return=1)
    pool = [0x100 + 4 * offset for offset in range(40)] + [0x300, 0x700, 0x10300, 0x301]
    for trial in range(4096):
        address = random_source.choice(pool)
        add(fetch=address if trial % 3 else random_source.choice(pool), pc=address,
            target=random_source.choice(pool), valid=random_source.randrange(2),
            conditional=random_source.randrange(2), taken=random_source.randrange(2),
            is_return=random_source.randrange(2), push=random_source.randrange(2), pop=random_source.randrange(2),
            reset=int(trial % 193 != 0), invalidate=int(trial % 151 == 0))
    return output


class ReturnStackTests(unittest.TestCase):
    def test_exact_changes(self):
        receipt = json.loads((ROOT / "change-receipt.json").read_text())
        for filename, record in receipt["files"].items():
            original = (BASE / "rtl" / filename).read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest().upper(), record["parent_sha256"])
            expected = original.decode()
            for before, after in record["substitutions"]:
                self.assertEqual(expected.count(before), 1)
                expected = expected.replace(before, after)
            actual = (ROOT / filename).read_bytes()
            self.assertEqual(actual, expected.encode())
            self.assertEqual(hashlib.sha256(actual).hexdigest().upper(), record["candidate_sha256"])

    def simulate(self, depth, mutation=None):
        source = (ROOT / "rv32_btb.sv").read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix="return-stack-") as temporary:
            work = Path(temporary)
            candidate = work / "rv32_btb.sv"
            candidate.write_text(source)
            original = (BASE / "rtl/rv32_btb.sv").read_text().replace("module rv32_btb #(", "module rv32_btb_reference #(")
            reference = work / "reference.sv"
            reference.write_text(original)
            data = work / "vectors.txt"
            rows = vectors(depth)
            data.write_text("\n".join(rows) + "\n")
            image = work / "test.vvp"
            compiled = subprocess.run(["iverilog", "-g2012", "-s", "return_stack_tb", f"-Preturn_stack_tb.DEPTH={depth}",
                                       "-o", str(image), str(candidate), str(reference), str(ROOT / "return_stack_tb.sv")],
                                      capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["vvp", str(image), "+vectors=" + str(data)], capture_output=True, text=True, timeout=60)
            output = executed.stdout + executed.stderr
            if mutation:
                self.assertNotEqual(executed.returncode, 0, output)
                self.assertIn("FAIL return_stack", output)
            else:
                self.assertEqual(executed.returncode, 0, output)
                self.assertIn(f"PASS return_stack depth={depth} vectors={len(rows)}", output)
            print(output.strip(), flush=True)

    def test_stack_depths_and_disabled_equivalence(self):
        for depth in (0, 1, 2, 4, 8):
            with self.subTest(depth=depth):
                self.simulate(depth)

    def test_eight_compiled_faults_rejected(self):
        mutations = (
            ("addresses[0]<=update_pc+32'd4;", "addresses[0]<=update_pc;"),
            ("else if (stack_pop && count!=0)", "else if (1'b0 && count!=0)"),
            ("if (!stack_pop || count==0)", "if (1'b1)"),
            ("assign stack_target=addresses[0];", "assign stack_target=addresses[RETURN_STACK_DEPTH-1];"),
            ("end else if (invalidate) begin\n                count<=0;", "end else if (invalidate) begin\n                count<=count;"),
            ("stack_available && return_entry[fetch_index] && !conditional[fetch_index]", "stack_available"),
            ("assign stack_available=count!=0;", "assign stack_available=1'b0;"),
            ("end else if (stack_push) begin", "end else if (stack_push && update_valid) begin"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                self.simulate(2, mutation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
