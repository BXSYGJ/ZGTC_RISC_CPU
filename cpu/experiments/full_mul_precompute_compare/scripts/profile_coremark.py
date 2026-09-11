import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


EVENT_NAMES = (
    "branch_resolutions",
    "branch_redirects",
    "jal_resolutions",
    "jal_redirects",
    "jalr_resolutions",
    "jalr_redirects",
    "memory_wait_cycles",
    "muldiv_wait_cycles",
    "fetch_wait_cycles",
    "frontend_empty_cycles",
    "retiring_cycles",
    "nonretiring_cycles",
)


def parse_events(line, cycles, retired):
    pattern = "EVENTS " + " ".join(name + r"=([0-9]+)" for name in EVENT_NAMES)
    match = re.fullmatch(pattern, line)
    if not match:
        raise ValueError("Malformed pipeline event row")
    events = dict(zip(EVENT_NAMES, map(int, match.groups())))
    if any(count > cycles for count in events.values()):
        raise ValueError("Pipeline event exceeds window cycles")
    if events["retiring_cycles"] != retired or events["retiring_cycles"] + events["nonretiring_cycles"] != cycles:
        raise ValueError("Pipeline retirement cycle conservation failed")
    for control in ("branch", "jal", "jalr"):
        if events[control + "_redirects"] > events[control + "_resolutions"]:
            raise ValueError("More redirects than resolved controls")
    if sum(events[name + "_resolutions"] for name in ("branch", "jal", "jalr")) > cycles:
        raise ValueError("Multiple control resolutions per cycle")
    return {"counts": events,
            "sampling": "Negative-edge pipeline state within the retirement-PC window; simultaneous categories overlap and are not causal stall-cycle attribution",
            "conditional_branch_redirect_percent": 100 * events["branch_redirects"] / events["branch_resolutions"] if events["branch_resolutions"] else None,
            "indirect_jump_redirect_percent": 100 * events["jalr_redirects"] / events["jalr_resolutions"] if events["jalr_resolutions"] else None}


def parse_symbols(text):
    symbols = []
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+) ([0-9a-fA-F]+) [tT] (\S+)", line)
        if match:
            start, size = int(match[1], 16), int(match[2], 16)
            if size > 0:
                symbols.append({"start": start, "end": start + size, "name": match[3]})
    if not symbols:
        raise ValueError("No sized executable symbols found")
    return symbols


def analyze(histogram, symbols_text):
    lines = histogram.splitlines()
    if not lines:
        raise ValueError("Empty profile")
    header = re.fullmatch(r"WINDOW start=([0-9a-f]{8}) stop=([0-9a-f]{8}) cycles=(\d+) retired=(\d+)", lines[0])
    if not header:
        raise ValueError("Invalid or missing profile window header")
    start, stop, cycles, retired = int(header[1], 16), int(header[2], 16), int(header[3]), int(header[4])
    if start == stop or start % 4 or stop % 4 or cycles < retired or retired < 1:
        raise ValueError("Invalid profile window/counters")
    events = None
    if len(lines) > 1 and lines[1].startswith("EVENTS"):
        events = parse_events(lines.pop(1), cycles, retired)
    symbols = parse_symbols(symbols_text)
    counts = {}
    functions = {}
    ambiguous = 0
    for line in lines[1:]:
        match = re.fullmatch(r"([0-9a-f]{8}) ([1-9]\d*)", line)
        if not match:
            raise ValueError("Malformed histogram row")
        address, count = int(match[1], 16), int(match[2])
        if address in counts or address % 4 or address >= 65536:
            raise ValueError("Duplicate or invalid histogram PC")
        counts[address] = count
        owners = [symbol["name"] for symbol in symbols if symbol["start"] <= address < symbol["end"]]
        if len(owners) == 1:
            functions[owners[0]] = functions.get(owners[0], 0) + count
        else:
            ambiguous += count
    if sum(counts.values()) != retired or counts.get(start) != 1 or stop in counts:
        raise ValueError("Histogram does not conserve the declared window")
    return {"status": "simulation_retirement_profile_not_a_coremark_score",
            "window_start_pc": f"{start:08x}", "window_stop_pc_exclusive": f"{stop:08x}",
            "cycles": cycles, "retired": retired, "ambiguous_or_unmapped_retired": ambiguous,
            "pipeline_events": events,
            "scope": "Retire iterate entry inclusive until stop_time entry exclusive; differs from CSR timing and does not assign stall cycles to functions",
            "functions": [{"name": name, "retired": count, "retired_percent": 100 * count / retired}
                          for name, count in sorted(functions.items(), key=lambda item: (-item[1], item[0]))]}


def main():
    parser = argparse.ArgumentParser(description="Analyze observed per-PC retirement counts without changing benchmark firmware")
    parser.add_argument("--histogram", required=True, type=Path)
    parser.add_argument("--symbols", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.histogram.read_text(encoding="utf-8-sig"), args.symbols.read_text(encoding="utf-8-sig"))
        result["inputs"] = {name: {"path": str(getattr(args, name)), "sha256": sha256(getattr(args, name).read_bytes()).hexdigest()}
                            for name in ("histogram", "symbols", "firmware", "elf")}
        with args.json.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
        print(json.dumps(result, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Profile rejected: {error}\n")


if __name__ == "__main__":
    main()
