import argparse
import json
import re
from pathlib import Path


def unique_match(pattern, text, label, flags=0):
    matches = list(re.finditer(pattern, text, flags))
    if len(matches) != 1:
        raise ValueError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def parse_reports(timing, log, clock_hz):
    if clock_hz <= 0:
        raise ValueError("Clock frequency must be positive")
    for label, value in (("Device", "PG2L200H"), ("Speed Grade", "-6"), ("Package", "FBB676")):
        found = unique_match(r"^\| " + label + r"\s*:\s*(\S+)\s*$", timing, label, re.M)
        if found.group(1) != value:
            raise ValueError(f"Unexpected {label}: {found.group(1)}")
    summary = unique_match(r"Design Summary\s*:\s*([^\r\n]+)", timing, "timing summary").group(1).strip()
    clock_name = "clk" if clock_hz == 27000000 else "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred"
    kind = "Declared" if clock_hz == 27000000 else r"Generated \(clk\)"
    clock = unique_match(r"^\s*" + re.escape(clock_name) + r"\s+([0-9.]+)\s+\{[^}]+\}\s+" + kind + r"\s+(\d+)", timing, "CPU clock", re.M)
    period, loads = float(clock.group(1)), int(clock.group(2))
    if abs(period - 1e9 / clock_hz) > 0.005 or loads < 1:
        raise ValueError("CPU clock period or synchronous load count does not match")
    performance = unique_match(re.escape(clock_name) + r"\s+([0-9.]+) MHz\s+([0-9.]+) MHz\s+([0-9.]+)\s+([0-9.]+)\s+(-?[0-9.]+)", timing, "CPU performance summary")
    if abs(float(performance.group(3)) - period) > 0.005:
        raise ValueError("Performance summary and clock table disagree")
    if abs(float(performance.group(1)) - 1000 / period) > 0.01:
        raise ValueError("Requested MHz and period disagree")
    if summary == "All Constraints Met." and float(performance.group(5)) < 0:
        raise ValueError("Negative setup slack contradicts passing timing summary")
    synthesis = int(unique_match(r"Total LUTs:\s+(\d+) of", log, "synthesis LUT count").group(1))
    if "Device Utilization Summary :" not in log:
        raise ValueError("Missing post-route resource table")
    physical = log.rsplit("Device Utilization Summary :", 1)[1]
    resources = {}
    for block in ("CLMA", "CLMS"):
        match = unique_match(r"\| Use of " + block + r"\s+\|[^\n]+\n\|\s+FF\s+\|\s*(\d+)[^\n]+\n\|\s+LUT\s+\|\s*(\d+)", physical, block + " physical resources")
        resources[block] = {"ff": int(match.group(1)), "lut": int(match.group(2))}
    resources["synthesis_luts"] = synthesis
    resources["post_route_luts"] = resources["CLMA"]["lut"] + resources["CLMS"]["lut"]
    resources["post_route_ffs"] = resources["CLMA"]["ff"] + resources["CLMS"]["ff"]
    if synthesis < 1 or resources["post_route_luts"] < 1 or resources["post_route_ffs"] < 1:
        raise ValueError("Invalid CPU resource count")
    for label in ("DRM", "GPLL"):
        match = unique_match(r"\| Use of " + label + r"\s+\|\s*([0-9.]+)\s*\|", physical, label + " resources")
        resources[label] = float(match.group(1))
    if resources["GPLL"] != (0 if clock_hz == 27000000 else 1):
        raise ValueError("GPLL resource count does not match clock source")
    return {"device": "PG2L200H-6FBB676", "clock_hz": clock_hz,
            "constraints_met": summary == "All Constraints Met.", "timing_summary": summary,
            "cpu_period_ns": period, "clock_loads": loads,
            "estimated_mhz_not_hardware_measurement": float(performance.group(2)),
            "setup_wns_ns": float(performance.group(5)), "resources": resources,
            "scbv_unset_warning": "SCBV has not been set" in log,
            "lut_metric": "post-route CLMA LUT plus CLMS LUT; do not add Distributed RAM again"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timing", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--clock-hz", required=True, type=int)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    result = parse_reports(args.timing.read_text(encoding="utf-8-sig"), args.log.read_text(encoding="utf-8-sig"), args.clock_hz)
    args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["constraints_met"]:
        raise SystemExit("Rejected: post-route timing constraints were not met")


if __name__ == "__main__":
    main()
