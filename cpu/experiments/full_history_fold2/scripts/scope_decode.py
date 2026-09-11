import argparse
import csv
import json
import re
from pathlib import Path


def checksum(records):
    value = 2166136261
    for timestamp, pins in records:
        value = ((value ^ timestamp) * 16777619) & 0xFFFFFFFF
        value = ((value ^ pins) * 16777619) & 0xFFFFFFFF
    return value


def parse_captures(text, expected_clock_hz=None):
    captures = []
    lines = text.replace("\r\n", "\n").splitlines()
    position = 0
    while position < len(lines):
        line = lines[position]
        if not line.startswith("SCOPE1"):
            position += 1
            continue
        header = re.fullmatch(r"SCOPE1 count=([0-9a-f]{8}) period=([0-9a-f]{8}) clock=([0-9a-f]{8}) trigger=([0-9a-f]{2})", line)
        if not header:
            raise ValueError("Malformed capture header")
        count, period, clock, trigger = [int(value, 16) for value in header.groups()]
        if count != 256 or not 200 <= period <= 100000 or clock not in (27000000, 154285714, 157500000) or trigger not in (1, 2):
            raise ValueError("Unsupported capture metadata")
        if expected_clock_hz is not None and clock != expected_clock_hz:
            raise ValueError("Capture clock differs from expected firmware clock")
        records = []
        for offset in range(1, count + 1):
            if position + offset >= len(lines):
                raise ValueError("Truncated samples")
            match = re.fullmatch(r"([0-9a-f]{8}):([0-9a-f]{2})", lines[position + offset])
            if not match:
                raise ValueError("Malformed sample")
            timestamp, pins = [int(value, 16) for value in match.groups()]
            if pins > 3 or (records and timestamp <= records[-1][0]):
                raise ValueError("Invalid pin bits or non-monotonic timestamp")
            records.append((timestamp, pins))
        footer_position = position + count + 1
        if footer_position >= len(lines):
            raise ValueError("Missing footer")
        footer = re.fullmatch(r"END checksum=([0-9a-f]{8}) late=([0-9a-f]{8})", lines[footer_position])
        if not footer:
            raise ValueError("Malformed footer")
        expected, late = [int(value, 16) for value in footer.groups()]
        if checksum(records) != expected or late > count:
            raise ValueError("Checksum mismatch or invalid late count")
        captures.append({"clock_hz": clock, "period_cycles": period, "trigger_mask": trigger,
                         "late_samples": late, "checksum": f"{expected:08x}", "records": records})
        position = footer_position + 1
    if not captures:
        raise ValueError("No complete captures")
    return captures


def transitions(capture, channel):
    records = capture["records"]
    return [(timestamp, (pins >> channel) & 1) for (previous_time, previous), (timestamp, pins) in zip(records, records[1:])
            if ((previous ^ pins) >> channel) & 1]


def decode_triggered_uart(capture, baud):
    records = capture["records"]
    if capture["trigger_mask"] != 2 or records[0][1] & 2 or baud <= 0:
        raise ValueError("UART frame must start at a captured RX falling edge")
    bit_cycles = capture["clock_hz"] / baud
    origin = records[0][0]
    def sample_at(relative):
        target = origin + relative * bit_cycles
        if target > records[-1][0]:
            raise ValueError("Capture is too short for the UART frame")
        candidates = [(timestamp, pins) for timestamp, pins in records if timestamp <= target]
        following = [timestamp for timestamp, pins in records if timestamp > target]
        if not candidates or not following or target-candidates[-1][0] > bit_cycles/3 or following[0]-target > bit_cycles/3:
            raise ValueError("Sampling is too sparse for reliable UART decoding")
        return (candidates[-1][1] >> 1) & 1
    if sample_at(0.5) != 0 or sample_at(9.5) != 1:
        raise ValueError("Bad UART start or stop level")
    return sum(sample_at(bit_index + 1.5) << bit_index for bit_index in range(8))


def waveform_svg(capture):
    records = capture["records"]
    first, last = records[0][0], records[-1][0]
    span = last - first
    if span <= 0:
        raise ValueError("Empty time span")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="330" viewBox="0 0 1200 330">',
             '<rect width="1200" height="330" fill="#0b1324"/>',
             '<g font-family="Arial,Microsoft YaHei,sans-serif" fill="#e2e8f0">',
             '<text x="24" y="32" font-size="22">ZGTC RV32I GPIO waveform capture</text>',
             f'<text x="24" y="58" font-size="14">256 samples | requested period {capture["period_cycles"]} cycles | late samples {capture["late_samples"]} | checksum {capture["checksum"]}</text>']
    for tick in range(6):
        xpos = 150 + tick * 200
        microseconds = span / capture["clock_hz"] * 1e6 * tick / 5
        parts += [f'<line x1="{xpos}" y1="85" x2="{xpos}" y2="260" stroke="#334155"/>',
                  f'<text x="{xpos}" y="285" text-anchor="middle" font-size="12">{microseconds:.1f} us</text>']
    for channel, label, color in ((0, "KEY1", "#22d3ee"), (1, "UART RX", "#a3e635")):
        baseline = 150 + channel * 90
        parts.append(f'<text x="24" y="{baseline-14}" font-size="16">{label}</text>')
        points = []
        previous_level = (records[0][1] >> channel) & 1
        for timestamp, pins in records:
            xpos = 150 + (timestamp - first) / span * 1000
            level = (pins >> channel) & 1
            points += [f"{xpos:.3f},{baseline-previous_level*40}", f"{xpos:.3f},{baseline-level*40}"]
            previous_level = level
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="2"/>')
    parts += ['<text x="24" y="315" font-size="12">Time relative to first sample; timestamps are CPU reads after GPIO load, not hardware edge timestamps.</text>', '</g></svg>']
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uart_log", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-uart", type=lambda value: int(value, 16))
    parser.add_argument("--baud", default=9600, type=int)
    parser.add_argument("--verify-key", action="store_true")
    parser.add_argument("--expected-clock", type=int, choices=(27000000, 157500000))
    args = parser.parse_args()
    captures = parse_captures(args.uart_log.read_text(encoding="utf-8-sig"), args.expected_clock)
    if args.expect_uart is not None:
        uart_captures = [capture for capture in captures if capture["trigger_mask"] == 2]
        if not uart_captures or any(decode_triggered_uart(capture, args.baud) != args.expect_uart for capture in uart_captures):
            raise ValueError("Captured UART waveform does not decode to the expected byte")
    if args.verify_key:
        key_captures = [capture for capture in captures if capture["trigger_mask"] == 1]
        if not key_captures or any([level for timestamp, level in transitions(capture, 0)] != [0, 1, 0] for capture in key_captures):
            raise ValueError("KEY waveform does not match the injected test sequence")
    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for index, capture in enumerate(captures):
        with (args.output / f"capture-{index}.csv").open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.writer(output)
            writer.writerow(("sample", "cycle_after_gpio_read", "time_us", "key1", "uart_rx"))
            for record_index, (timestamp, pins) in enumerate(capture["records"]):
                writer.writerow((record_index, timestamp, timestamp / capture["clock_hz"] * 1e6, pins & 1, (pins >> 1) & 1))
        (args.output / f"capture-{index}.svg").write_text(waveform_svg(capture), encoding="utf-8")
        summary.append({name: value for name, value in capture.items() if name != "records"})
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"PASS scope captures={len(captures)} samples={256*len(captures)} checksum and waveform checks complete")


if __name__ == "__main__":
    main()
