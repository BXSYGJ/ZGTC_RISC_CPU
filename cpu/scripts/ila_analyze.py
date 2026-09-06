import argparse
import csv
import html
import json
import re
from collections import Counter
from pathlib import Path


PC_NAMES = [f"board/soc/core/{stage}_pc[{bit}]" for stage in ("ex", "id", "if") for bit in range(32)]
CONTROL_NAMES = [
    "board/soc/core/pipeline_valid[0]", "board/soc/core/pipeline_valid[1]",
    "board/soc/core/pipeline_valid[2]", "board/soc/unused_pipeline_valid[3]",
    "board/soc/core/board/unused_trace_valid", "board/soc/core/id_fire",
    "board/soc/core/ex_fire", "board/soc/core/mem_sent", "board/soc/core/mem_load",
    "board/soc/core/mem_flush", "board/soc/i_rsp_valid",
    "board/soc/memory_system/cache_rsp_valid[1]",
    "board/soc/memory_system/master_cmd_valid[0]",
]
EXPECTED_HEADER = ["Sample Index"] + PC_NAMES + CONTROL_NAMES


def read_capture(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    if not rows or rows[0] != EXPECTED_HEADER:
        raise ValueError("CSV header does not match the verified 109-channel FIC")
    if len(rows) != 1025:
        raise ValueError("Expected exactly 1024 captured samples")
    result = []
    for index, row in enumerate(rows[1:]):
        if len(row) != 110 or row[0] != str(index) or any(value not in ("0", "1") for value in row[1:]):
            raise ValueError(f"Invalid sample order, width or binary data at {index}")
        bits = [int(value) for value in row[1:]]
        decoded = {f"{stage}_pc": sum(bits[offset + bit] << bit for bit in range(32))
                   for stage, offset in (("ex", 0), ("id", 32), ("if", 64))}
        decoded.update(zip(("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid",
                            "id_fire", "ex_fire", "mem_sent", "mem_load", "redirect",
                            "i_response", "d_response", "i_command"), bits[96:]))
        if (decoded["id_fire"] and not decoded["id_valid"]) or (decoded["ex_fire"] and not decoded["ex_valid"]):
            raise ValueError("Pipeline fire/valid invariant violated; check signal mapping")
        result.append(decoded)
    for previous, following in zip(result, result[1:]):
        if previous["id_fire"] and (not following["ex_valid"] or following["ex_pc"] != previous["id_pc"]):
            raise ValueError("ID-to-EX transfer mismatch across adjacent samples")
        if previous["ex_fire"] and not following["mem_valid"]:
            raise ValueError("EX-to-MEM valid transfer mismatch across adjacent samples")
    return result


def read_symbols(path):
    symbols = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+) ([0-9a-fA-F]+) [Tt] (\S+)", line.strip())
        if match:
            address, size, name = match.groups()
            symbols.append((int(address, 16), int(size, 16), name))
    if not symbols:
        raise ValueError("No sized executable symbols in nm -S output")
    return symbols


def function_at(address, symbols):
    for start, size, name in symbols:
        if start <= address < start + size:
            return name
    return "unmapped"


def summarize(samples, symbols):
    count = len(samples)
    executed = Counter(function_at(sample["ex_pc"], symbols) for sample in samples if sample["ex_fire"])
    return {
        "samples": count, "clock_hz": 27000000, "window_us": count / 27,
        "first_to_last_us": (count - 1) / 27,
        "temporal_pairs_checked": count - 1,
        "wb_events": sum(sample["wb_valid"] for sample in samples),
        "window_wb_per_cycle": sum(sample["wb_valid"] for sample in samples) / count,
        "stage_occupied_cycles": {stage: sum(sample[f"{stage}_valid"] for sample in samples)
                                  for stage in ("if", "id", "ex", "mem", "wb")},
        "id_held_cycles": sum(sample["id_valid"] and not sample["id_fire"] for sample in samples),
        "ex_held_cycles": sum(sample["ex_valid"] and not sample["ex_fire"] for sample in samples),
        "load_response_wait_cycles": sum(sample["mem_valid"] and sample["mem_load"] and sample["mem_sent"] and not sample["d_response"] for sample in samples),
        "redirect_cycles": sum(sample["redirect"] for sample in samples),
        "i_command_high_cycles": sum(sample["i_command"] for sample in samples),
        "ex_fire_function_counts": dict(executed.most_common()),
    }


def render_svg(samples, title, start=0, length=128):
    if start < 0 or length < 2 or start + length > len(samples):
        raise ValueError("Invalid waveform display window")
    signals = ("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid", "id_fire", "ex_fire", "mem_sent", "d_response", "redirect")
    parts = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1400\" height=\"700\" viewBox=\"0 0 1400 700\">",
             "<rect width=\"1400\" height=\"700\" fill=\"#0b1324\"/>",
             "<g fill=\"#e2e8f0\" font-family=\"Arial, sans-serif\">",
             f"<text x=\"24\" y=\"32\" font-size=\"20\">{html.escape(title)}</text>",
             f"<text x=\"24\" y=\"58\" font-size=\"14\">Physical JTAG ILA | 27 MHz | samples {start}..{start+length-1} | one sample per CPU clock</text>"]
    for tick in range(9):
        xpos = 170 + tick * 148
        parts += [f"<path d=\"M{xpos} 80V620\" stroke=\"#334155\"/>",
                  f"<text x=\"{xpos}\" y=\"645\" text-anchor=\"middle\" font-size=\"12\">{start+tick*length//8}</text>"]
    for row, signal in enumerate(signals):
        baseline = 110 + row * 50
        parts.append(f"<text x=\"20\" y=\"{baseline}\" font-size=\"14\">{signal}</text>")
        points = []
        for index, sample in enumerate(samples[start:start+length]):
            left = 170 + index * 1184 / length
            right = 170 + (index+1) * 1184 / length
            ypos = baseline - sample[signal] * 25
            points.extend((f"{left:.3f},{ypos}", f"{right:.3f},{ypos}"))
        parts.append(f"<polyline points=\"{' '.join(points)}\" stroke=\"#22d3ee\" stroke-width=\"1.4\" fill=\"none\"/>")
    parts += ["<text x=\"24\" y=\"683\" font-size=\"13\">Local window only; occupied/held cycles are not automatically data hazards or global IPC.</text>", "</g></svg>"]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    symbols = read_symbols(args.symbols)
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for path in args.captures:
        samples = read_capture(path)
        result = summarize(samples, symbols)
        result["source"] = path.name
        results.append(result)
        (args.output / f"{path.stem}.svg").write_text(render_svg(samples, path.stem), encoding="utf-8")
        with (args.output / f"{path.stem}-decoded.csv").open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(output, fieldnames=list(samples[0]))
            writer.writeheader()
            writer.writerows(samples)
    (args.output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
