import argparse
import json
from pathlib import Path

from check_performance_target import assess
from compare_coremark import read_case


def assess_candidate(case, expected_clock_hz):
    if case.get("source_snapshot_verified") is not True:
        raise ValueError("Frequency candidates require verified production source snapshots")
    report = assess(case, expected_clock_hz=expected_clock_hz)
    report["acceptance_profile"] = "explicit_frequency_candidate"
    return report


def main():
    parser = argparse.ArgumentParser(description="Check an explicit >=120 MHz candidate against unchanged execution and resource floors")
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--uart", required=True, type=Path)
    parser.add_argument("--clock-hz", required=True, type=int)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        report = assess_candidate(read_case(args.build, args.uart), args.clock_hz)
        encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.json:
            with args.json.open("x", encoding="utf-8") as output:
                output.write(encoded)
        print(encoded)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Invalid frequency candidate evidence: {error}\n")
    if report["status"] != "numeric_target_pass":
        parser.exit(2, "Frequency candidate rejected; diagnostic report retained.\n")


if __name__ == "__main__":
    main()

