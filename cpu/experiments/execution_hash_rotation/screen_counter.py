import csv
import json
from collections import Counter
from pathlib import Path

from screen_rotations import ROOT, RotatedReplay, digest, folded_index


class CounterReplay(RotatedReplay):
    def __init__(self, mode):
        if mode not in ("saturating", "hysteresis", "fast", "saturating_strong", "hysteresis_strong", "fast_strong"):
            raise ValueError("Unsupported counter state machine")
        super().__init__(4)
        self.mode = mode

    def transition(self, state, taken):
        tables = {
            "saturating": ((0, 1), (0, 2), (1, 3), (2, 3)),
            "hysteresis": ((0, 1), (0, 3), (0, 3), (2, 3)),
            "fast": ((0, 2), (0, 2), (1, 3), (1, 3)),
        }
        return tables[self.mode.removesuffix("_strong")][state][taken]

    def step(self, pc, target, taken, conditional):
        index = folded_index(pc, 4)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        bank = history
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][bank] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [(3 if taken else 0) if self.mode.endswith("_strong") else (2 if taken else 1)] * 8
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][bank]
            self.counters[index][bank] = self.transition(counter, taken)
            self.history[index] = ((history << 1) | taken) & 7
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction


def main():
    directory = Path(__file__).resolve().parent
    output = directory / "counter-screen.json"
    if output.exists():
        raise ValueError("Refusing to overwrite screening evidence")
    prior = json.loads((directory / "screen.json").read_text())
    report_path = ROOT / "build/wb-byte-branch-profile.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    trace = ROOT / "build/wb-byte-branch-profile-stage/build/compiled" / report["build"] / "coremark.sim.uart.branches.csv"
    if digest(trace) != prior["trace_sha256"] or digest(report_path) != prior["report_sha256"]:
        raise ValueError("Validated input changed")
    if digest(directory / "screen_rotations.py") != prior["script_sha256"]:
        raise ValueError("Validated screening script changed")
    models = {mode: CounterReplay(mode) for mode in ("saturating", "hysteresis", "fast", "saturating_strong", "hysteresis_strong", "fast_strong")}
    counts = {fold: Counter() for fold in models}
    records = 0
    ended = False
    with trace.open(newline="", encoding="utf-8") as stream:
        rows = csv.reader(stream)
        next(rows)
        next(rows)
        for row in rows:
            if row[0] == "END":
                if int(row[1]) != records or next(rows, None) is not None:
                    raise ValueError("Trace trailer mismatch")
                ended = True
                break
            records += 1
            pc, target, actual, observed = (int(row[index], 16) for index in (2, 4, 5, 6))
            taken, conditional = int(row[7]), int(row[8])
            predictions = {fold: model.step(pc, target, taken, conditional) for fold, model in models.items()}
            if int(row[1]) and conditional:
                if predictions["saturating"] != observed:
                    raise ValueError("Baseline window prediction mismatch")
                for fold, prediction in predictions.items():
                    counts[fold]["resolutions"] += 1
                    counts[fold]["redirects"] += prediction != actual
                    counts[fold]["improved"] += prediction == actual and observed != actual
                    counts[fold]["regressed"] += prediction != actual and observed == actual
    if not ended or records != prior["records"]:
        raise ValueError("Incomplete trace")
    for fold in counts:
        counts[fold]["redirects_reduced"] = counts["saturating"]["redirects"] - counts[fold]["redirects"]
        if counts[fold]["redirects_reduced"] != counts[fold]["improved"] - counts[fold]["regressed"]:
            raise ValueError("Conservation failed")
    result = {"schema": 1, "scope": "historical resolution-order proxy, not RTL cycles or score", "records": records,
              "trace_sha256": digest(trace), "script_sha256": digest(Path(__file__)), "baseline_mode": "saturating",
              "history_bits": 3, "counter_banks": 8, "candidates": counts, "hardware_validated": False}
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()


