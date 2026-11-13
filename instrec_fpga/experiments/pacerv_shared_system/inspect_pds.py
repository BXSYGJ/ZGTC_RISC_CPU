"""Check the ten PDS timing summaries and the frozen build inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timing_summary(text: str) -> dict:
    heading = re.compile(r"^(Setup|Hold|Recovery|Removal|Minimum Pulse Width) Summary\((Slow|Fast) Corner\):", re.M)
    sections = list(heading.finditer(text))
    tables = []
    row = re.compile(r"^\s*(\S+)\s+(?:(\S+)\s+)?(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$")
    for index, match in enumerate(sections):
        # Summaries are followed by a line of '='. Detailed path dumps follow
        # the tenth table and must not be mistaken for summary rows.
        body = text[match.end():sections[index+1].start() if index+1 < len(sections) else None]
        body = body.split("\n=", 1)[0]
        rows = []
        for line in body.splitlines():
            values = row.fullmatch(line)
            if values:
                rows.append({"launch_clock": values[1], "capture_clock": values[2] or values[1],
                             "slack_ns": float(values[3]), "total_negative_slack_ns": float(values[4]),
                             "failing_endpoints": int(values[5]), "total_endpoints": int(values[6])})
        tables.append({"check": match[1], "corner": match[2], "rows": rows,
                       "passed": bool(rows) and all(r["slack_ns"] >= 0 and r["failing_endpoints"] == 0 for r in rows)})
    complete = len(tables) == 10 and all(t["rows"] for t in tables)
    declared_met = bool(re.search(r"Design Summary\s*:\s*All Constraints Met", text))
    return {"complete_ten_tables": complete, "design_summary_met": declared_met,
            "all_constraints_met": complete and declared_met and all(t["passed"] for t in tables),
            "tables": tables}


def clock_contract(text: str, manifest: dict) -> dict:
    expected = {clock: manifest[key] for clock, key in
                (("ddrphy_sysclk", "system_clock_hz"), ("pix_clk", "pixel_clock_hz"))
                if key in manifest}
    reported = {name: float(mhz) * 1e6 for name, mhz in re.findall(
        r"^\s*(\S+)\s+(\d+\.\d+)\s+MHz\s+", text, re.M)}
    checks = {name: {"expected_hz": hz, "reported_hz": reported.get(name),
                     "passed": name in reported and abs(reported[name] - hz) <= max(1000, hz * 1e-5)}
              for name, hz in expected.items()}
    return {"checks": checks, "passed": all(c["passed"] for c in checks.values())}


def inspect(run: Path) -> dict:
    manifest = json.loads((run / "INPUTS.json").read_text(encoding="utf-8"))
    changed = [entry["path"] for entry in manifest["files"]
               if not (run / "inputs" / entry["path"]).is_file()
               or sha256(run / "inputs" / entry["path"]) != entry["sha256"]]
    reports = list((run / "report_timing").glob("*.rtr"))
    if len(reports) != 1:
        raise ValueError("Exactly one timing report is required: " + str(run))
    report = reports[0]
    report_text = report.read_text(encoding="utf-8", errors="replace")
    timing = timing_summary(report_text)
    clocks = clock_contract(report_text, manifest)
    bits = list((run / "generate_bitstream").glob("*.sbit"))
    bit = bits[0] if len(bits) == 1 else None
    utilization = {}
    for prr in (run / "place_route").glob("*.prr"):
        content = prr.read_text(encoding="utf-8", errors="replace")
        marker = "Device Utilization Summary Of Each Module:"
        if marker not in content:
            continue
        # The first data row is the complete top; child rows are additional
        # breakdowns and must not be summed with their parents.
        lines = content.split(marker, 1)[1].splitlines()
        for line in lines:
            fields = [f.strip() for f in line.split("|")]
            if len(fields) > 7 and re.fullmatch(r"[\d.]+", fields[2]):
                utilization = {key: float(value) if "." in value else int(value)
                               for key, value in zip(("lut", "ff", "distributed_ram", "apm", "drm"), fields[2:7])}
                break
    return {"run": str(run.resolve()), "scope": manifest["scope"], "target": manifest["target"],
            "frozen_input_count": len(manifest["files"]), "changed_inputs": changed,
            "timing_report": str(report.resolve()), "timing_sha256": sha256(report),
            "timing": timing, "clock_contract": clocks, "routed_resources": utilization,
            "bitstream": str(bit.resolve()) if bit else None,
            "bitstream_sha256": sha256(bit) if bit else None,
            "qualified": not changed and timing["all_constraints_met"] and clocks["passed"] and bit is not None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--require-qualified", action="store_true")
    args = parser.parse_args()
    result = inspect(args.run)
    destination = args.run / "QUALIFICATION.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {k: v for k, v in result.items() if k != "timing"}
    compact["timing"] = {k: v for k, v in result["timing"].items() if k != "tables"}
    print(json.dumps(compact, indent=2))
    if args.require_qualified and not result["qualified"]:
        raise SystemExit(2)
