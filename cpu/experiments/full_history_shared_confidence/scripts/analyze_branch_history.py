import argparse
import csv
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import re


HEADER = ["cycle", "window", "pc", "instruction", "target", "next_pc", "predicted_pc", "taken", "conditional"]


def folded_index(pc):
    high = (pc >> 10) & 255
    return ((pc >> 2) ^ ((high << 4) | (high >> 4))) & 255


class ResolutionReplay:
    def __init__(self, history_bits=0):
        if type(history_bits) is not int or not 0 <= history_bits <= 8:
            raise ValueError("Unsupported history width")
        self.history_bits = history_bits
        self.history = 0
        self.valid = [False] * 256
        self.tags = [0] * 256
        self.targets = [0] * 256
        self.conditional = [False] * 256
        self.counters = [1] * 256

    def step(self, pc, target, taken, conditional):
        index = folded_index(pc)
        tag = pc >> 10
        counter_index = index ^ self.history if self.history_bits else index
        hit = self.valid[index] and self.tags[index] == tag
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[counter_index] >= 2) else pc + 4
        if self.history_bits:
            if conditional:
                self.counters[counter_index] = min(3, self.counters[counter_index] + 1) if taken else max(0, self.counters[counter_index] - 1)
                self.history = ((self.history << 1) | taken) & ((1 << self.history_bits) - 1)
        elif not hit or self.conditional[index] != conditional:
            self.counters[index] = 2 if taken else 1
        elif taken:
            self.counters[index] = min(3, self.counters[index] + 1)
        else:
            self.counters[index] = max(0, self.counters[index] - 1)
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction


class LocalResolutionReplay:
    def __init__(self, history_bits):
        if type(history_bits) is not int or not 1 <= history_bits <= 3:
            raise ValueError("Unsupported local history width")
        self.history_bits = history_bits
        self.valid = [False] * 256
        self.tags = [0] * 256
        self.targets = [0] * 256
        self.conditional = [False] * 256
        self.history = [0] * 256
        self.counters = [[1] * (1 << history_bits) for _ in range(256)]

    def step(self, pc, target, taken, conditional):
        index = folded_index(pc)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][history] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [2 if taken else 1] * (1 << self.history_bits)
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][history]
            self.counters[index][history] = min(3, counter + 1) if taken else max(0, counter - 1)
            self.history[index] = ((history << 1) | taken) & ((1 << self.history_bits) - 1)
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction


def unsigned(text, base=10):
    pattern = r"[0-9]+" if base == 10 else r"[0-9a-f]{8}"
    if not re.fullmatch(pattern, text):
        raise ValueError("Invalid integer field")
    return int(text, base)


def decoded_target(pc, instruction):
    opcode = instruction & 127
    if opcode == 99:
        if (instruction >> 12) & 7 not in (0, 1, 4, 5, 6, 7):
            raise ValueError("Reserved branch encoding")
        immediate = (((instruction >> 31) & 1) << 12) | (((instruction >> 7) & 1) << 11) | (((instruction >> 25) & 63) << 5) | (((instruction >> 8) & 15) << 1)
        if immediate & 4096:
            immediate -= 8192
    elif opcode == 111:
        immediate = (((instruction >> 31) & 1) << 20) | (((instruction >> 12) & 255) << 12) | (((instruction >> 20) & 1) << 11) | (((instruction >> 21) & 1023) << 1)
        if immediate & 1048576:
            immediate -= 2097152
    elif opcode == 103 and ((instruction >> 12) & 7) == 0:
        return None
    else:
        raise ValueError("Not a supported control instruction")
    return (pc + immediate) & 0xffffffff


def analyze(text):
    reader = csv.reader(io.StringIO(text))
    metadata = next(reader, [])
    if len(metadata) != 8 or metadata[:3] != ["schema", "1", "start_pc"] or metadata[4] != "stop_pc" or metadata[6:] != ["sampling", "post_negative_edge"]:
        raise ValueError("Unsupported branch trace metadata")
    start, stop = unsigned(metadata[3], 16), unsigned(metadata[5], 16)
    if start == stop or start % 4 or stop % 4 or max(start, stop) >= 65536:
        raise ValueError("Invalid profile boundaries")
    if next(reader, []) != HEADER:
        raise ValueError("Unexpected branch trace header")
    models = {width: ResolutionReplay(width) for width in (0, 1, 2, 4, 6, 8)}
    models.update({"local_" + str(width): LocalResolutionReplay(width) for width in (1, 2, 3)})
    replay_counts = {width: Counter() for width in models}
    observed = Counter()
    by_pc = {}
    count = 0
    previous_cycle = 0
    phase = 0
    footer = None
    for row in reader:
        if row and row[0] == "END":
            if len(row) != 4 or next(reader, None) is not None:
                raise ValueError("Invalid or nonterminal trace footer")
            footer = [unsigned(value) for value in row[1:]]
            break
        if len(row) != len(HEADER):
            raise ValueError("Malformed branch trace row")
        cycle, window = unsigned(row[0]), unsigned(row[1])
        pc, instruction, target, actual, predicted = (unsigned(value, 16) for value in row[2:7])
        taken, conditional = unsigned(row[7]), unsigned(row[8])
        if cycle <= previous_cycle or window not in (0, 1) or taken not in (0, 1) or conditional not in (0, 1):
            raise ValueError("Invalid cycle or binary field")
        if any(address % 4 or address >= 65536 for address in (pc, target, actual, predicted)):
            raise ValueError("Control address outside aligned 64 KiB domain")
        expected_target = decoded_target(pc, instruction)
        if expected_target is not None and expected_target != target:
            raise ValueError("Instruction immediate target mismatch")
        opcode = instruction & 127
        if conditional != (opcode == 99) or (not conditional and not taken):
            raise ValueError("Control class or taken field mismatch")
        if actual != (target if taken else pc + 4):
            raise ValueError("Resolved next-PC mismatch")
        if window:
            if phase == 2:
                raise ValueError("Profile window restarted")
            phase = 1
        elif phase == 1:
            phase = 2
        previous_cycle = cycle
        count += 1
        kind = "branch" if conditional else ("jal" if opcode == 111 else "jalr")
        misses = {}
        for width, model in models.items():
            proxy = model.step(pc, target, taken, conditional)
            misses[width] = proxy != actual
            if window:
                replay_counts[width][kind + "_resolutions"] += 1
                replay_counts[width][kind + "_redirects"] += misses[width]
                replay_counts[width]["prediction_differs_from_observed"] += proxy != predicted
        if not window:
            continue
        observed[kind + "_resolutions"] += 1
        observed[kind + "_redirects"] += predicted != actual
        if pc not in by_pc:
            by_pc[pc] = {"instruction": f"{instruction:08x}", "kind": kind, "resolutions": 0, "redirects": 0, "taken": 0}
        entry = by_pc[pc]
        if entry["instruction"] != f"{instruction:08x}":
            raise ValueError("Instruction changed at a profiled PC")
        entry["resolutions"] += 1
        entry["redirects"] += predicted != actual
        entry["taken"] += taken
        if conditional and target != pc + 4:
            observed["branch_direction_redirects"] += (predicted != pc + 4) != bool(taken)
            observed["branch_taken_target_redirects"] += taken and predicted != pc + 4 and predicted != target
    if footer is None or footer[0] != count or phase != 2:
        raise ValueError("Incomplete branch trace or record conservation failure")
    cycles, retired = footer[1:]
    resolutions = sum(observed[kind + "_resolutions"] for kind in ("branch", "jal", "jalr"))
    if not 0 < resolutions <= retired <= cycles:
        raise ValueError("Invalid window count conservation")
    return {
        "status": "branch_resolution_profile_and_proxy_replay_not_hardware_or_score",
        "start_pc": f"{start:08x}", "stop_pc": f"{stop:08x}", "total_records": count,
        "window_cycles": cycles, "window_retired": retired,
        "observed": dict(observed),
        "replay": {str(width): dict(counts) for width, counts in replay_counts.items()},
        "replay_scope": "Resolution-order lookup/update with warmup; omits in-flight lookup timing, stalls, speculative history, and wrong-path fetches. Never convert proxy redirects to saved cycles or CoreMark scores.",
        "hotspots": [{"pc": f"{pc:08x}", **entry} for pc, entry in sorted(by_pc.items(), key=lambda item: (-item[1]["redirects"], item[0]))],
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze observed branch decisions and bounded proxy histories")
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.trace.read_bytes()
        result = analyze(raw.decode("ascii"))
        result["trace_sha256"] = sha256(raw).hexdigest().upper()
        with args.json.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
        print(json.dumps({key: value for key, value in result.items() if key != "hotspots"}, indent=2))
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, "Branch profile rejected: " + str(error) + "\n")


if __name__ == "__main__":
    main()
