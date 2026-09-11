import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_branch_history import LocalResolutionReplay, analyze


def folded_index(pc, rotation):
    if type(rotation) is not int or not 0 <= rotation < 8:
        raise ValueError("Rotation must be 0..7")
    high = (pc >> 10) & 255
    return ((pc >> 2) ^ ((high << rotation) | (high >> (8 - rotation)))) & 255


class RotatedReplay(LocalResolutionReplay):
    def __init__(self, rotation):
        folded_index(0, rotation)
        super().__init__(3)
        self.rotation = rotation

    def step(self, pc, target, taken, conditional):
        index = folded_index(pc, self.rotation)
        tag = pc >> 10
        hit = self.valid[index] and self.tags[index] == tag
        history = self.history[index]
        prediction = self.targets[index] if hit and (not self.conditional[index] or self.counters[index][history] >= 2) else pc + 4
        if not hit or self.conditional[index] != conditional:
            self.counters[index] = [2 if taken else 1] * 8
            self.history[index] = taken if conditional else 0
        elif conditional:
            counter = self.counters[index][history]
            self.counters[index][history] = min(3, counter + 1) if taken else max(0, counter - 1)
            self.history[index] = ((history << 1) | taken) & 7
        self.valid[index] = True
        self.tags[index] = tag
        self.targets[index] = target
        self.conditional[index] = bool(conditional)
        return prediction


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def main():
    output = Path(__file__).resolve().parent / "screen.json"
    if output.exists():
        raise ValueError("Screen exists; do not overwrite evidence")
    baseline_btb = ROOT / "build/regfile-valid-fanout-stage/rtl/rv32_btb.sv"
    if digest(baseline_btb) != "BBB08D9A074D31CF846B26B1BCF4456C991AFA03068A09EF4B96BEC46823F2DB":
        raise ValueError("Accepted baseline predictor changed")
    report_path = ROOT / "build/wb-byte-branch-profile.json"
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    trace = ROOT / "build/wb-byte-branch-profile-stage/build/compiled" / report["build"] / "coremark.sim.uart.branches.csv"
    if digest(trace) != report["trace_sha256"] or digest(trace) != "5B716144F4496B1101026DDC0D4E671C4B9D81056C5C58C236800A237EE5533F":
        raise ValueError("Historical branch trace changed")
    if analyze(trace.read_text(encoding="utf-8")) != report["analysis"]:
        raise ValueError("Historical trace analysis does not reproduce")
    models = {rotation: RotatedReplay(rotation) for rotation in range(8)}
    counts = {rotation: Counter() for rotation in range(8)}
    records = 0
    with trace.open(newline="", encoding="utf-8") as stream:
        rows = csv.reader(stream)
        next(rows)
        next(rows)
        for row in rows:
            if row[0] == "END":
                if int(row[1]) != records or next(rows, None) is not None:
                    raise ValueError("Trace end count mismatch")
                break
            records += 1
            window = int(row[1])
            pc, target, actual, observed = (int(row[index], 16) for index in (2, 4, 5, 6))
            taken, conditional = int(row[7]), int(row[8])
            predictions = {rotation: model.step(pc, target, taken, conditional) for rotation, model in models.items()}
            if window and conditional:
                if predictions[4] != observed:
                    raise ValueError("Baseline proxy differs from observed conditional prediction")
                for rotation, prediction in predictions.items():
                    counts[rotation]["resolutions"] += 1
                    counts[rotation]["redirects"] += prediction != actual
                    counts[rotation]["improved"] += prediction == actual and predictions[4] != actual
                    counts[rotation]["regressed"] += prediction != actual and predictions[4] == actual
    if records != report["analysis"]["total_records"]:
        raise ValueError("Trace records mismatch")
    for rotation in counts:
        counts[rotation]["redirects_reduced"] = counts[4]["redirects"] - counts[rotation]["redirects"]
        if counts[rotation]["redirects_reduced"] != counts[rotation]["improved"] - counts[rotation]["regressed"]:
            raise ValueError("Improvement accounting mismatch")
    result = {"schema": 1, "scope": "historical resolution-order proxy only; not current RTL cycles, timing, area, or CoreMark score", "records": records,
              "predictor_sha256": digest(baseline_btb), "report_sha256": digest(report_path), "trace_sha256": digest(trace), "script_sha256": digest(Path(__file__)),
              "baseline_rotation": 4, "candidates": counts, "hardware_validated": False}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
