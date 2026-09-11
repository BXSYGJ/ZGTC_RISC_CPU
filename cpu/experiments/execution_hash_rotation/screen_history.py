import csv
import json
from collections import Counter
from pathlib import Path

from screen_rotations import ROOT, RotatedReplay, digest, folded_index


class FoldedHistoryReplay(RotatedReplay):
    def __init__(self, fold):
        if type(fold) is not int or not 0 <= fold <= 7:
            raise ValueError("Fold must be 0..7")
        super().__init__(4)
        self.fold = fold

    def bank(self, history):
        return (history & 7) ^ (self.fold if history & 8 else 0)

    def step(self, pc, target, taken, conditional):
        index = folded_index(pc, 4)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        bank = self.bank(history)
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][bank] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [2 if taken else 1] * 8
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][bank]
            self.counters[index][bank] = min(3, counter + 1) if taken else max(0, counter - 1)
            self.history[index] = ((history << 1) | taken) & 15
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction


def main():
    directory = Path(__file__).resolve().parent
    output = directory / "history-screen.json"
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
    models = {fold: FoldedHistoryReplay(fold) for fold in range(8)}
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
                if predictions[0] != observed:
                    raise ValueError("Baseline window prediction mismatch")
                for fold, prediction in predictions.items():
                    counts[fold]["resolutions"] += 1
                    counts[fold]["redirects"] += prediction != actual
                    counts[fold]["improved"] += prediction == actual and observed != actual
                    counts[fold]["regressed"] += prediction != actual and observed == actual
    if not ended or records != prior["records"]:
        raise ValueError("Incomplete trace")
    for fold in counts:
        counts[fold]["redirects_reduced"] = counts[0]["redirects"] - counts[fold]["redirects"]
        if counts[fold]["redirects_reduced"] != counts[fold]["improved"] - counts[fold]["regressed"]:
            raise ValueError("Conservation failed")
    result = {"schema": 1, "scope": "historical resolution-order proxy, not RTL cycles or score", "records": records,
              "trace_sha256": digest(trace), "script_sha256": digest(Path(__file__)), "baseline_fold": 0,
              "history_bits": 4, "counter_banks": 8, "candidates": counts, "hardware_validated": False}
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

