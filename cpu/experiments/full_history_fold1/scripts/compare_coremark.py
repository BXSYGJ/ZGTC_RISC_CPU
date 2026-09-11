import argparse
from hashlib import sha256
import json
import re
from pathlib import Path

from check_coremark import parse_result
from pds_report import parse_reports


def verify_sources(build, manifest):
    snapshot = manifest.get("SourceSnapshot")
    if snapshot is None:
        return False
    if not isinstance(snapshot, dict) or type(snapshot.get("Schema")) is not int or snapshot["Schema"] != 1:
        raise ValueError("Invalid PDS source snapshot schema")
    files = snapshot.get("Files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Empty PDS source snapshot")
    root = build / "source"
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Missing or linked PDS source snapshot")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Linked PDS source input")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(files):
        raise ValueError("PDS source snapshot inventory differs")
    for relative, expected in files.items():
        if not re.fullmatch(r"(?:rtl|fpga|constraints)/[A-Za-z0-9_.-]+", relative):
            raise ValueError("Invalid PDS source relative path")
        if not isinstance(expected, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", expected):
            raise ValueError("Invalid PDS source hash")
        if sha256((root / relative).read_bytes()).hexdigest() != expected.lower():
            raise ValueError("PDS source snapshot hash mismatch")
    return True


def cache_geometry(manifest):
    data_sets = manifest["CacheSetBits"]
    instruction_sets = manifest.get("ICacheSetBits", data_sets)
    if any(type(width) is not int or not 1 <= width <= 8 for width in (data_sets, instruction_sets)):
        raise ValueError("Invalid cache geometry in manifest")
    return data_sets, instruction_sets


def read_case(build, uart):
    raw = uart.read_bytes()
    if b"ZGTC RTL_SIMULATION_ONLY" in raw:
        raise ValueError("RTL simulation cannot be used as hardware evidence")
    manifest = json.loads((build / "manifest.json").read_text(encoding="utf-8-sig"))
    source_verified = verify_sources(build, manifest)
    report = parse_reports((build / "report_timing/pds_soc_top.rtr").read_text(encoding="utf-8-sig"),
                           (build / "run.log").read_text(encoding="utf-8-sig"), manifest["ClockHz"])
    if manifest["Device"] != "PG2L200H-6FBB676" or not manifest["TimingConstraintsMet"] or not report["constraints_met"]:
        raise ValueError("Both implementations must pass the target-device timing gate")
    if report != manifest["ResourceSummary"]:
        raise ValueError("Manifest resources differ from independently parsed PDS reports")
    hashes = {}
    for relative, key in (("firmware.hex", "FirmwareSha256"), ("generate_bitstream/pds_soc_top.sbit", "BitstreamSha256")):
        hashes[key] = sha256((build / relative).read_bytes()).hexdigest()
        if hashes[key] != manifest[key].lower():
            raise ValueError(f"Artifact hash mismatch: {relative}")
    for key in ("Predictor", "LoadUseBubble", "CacheEnabled", "FastICacheHit"):
        if type(manifest[key]) is not int or manifest[key] not in (0, 1):
            raise ValueError(f"Invalid binary configuration: {key}")
    enable_m = manifest.get("EnableM", 0)
    if type(enable_m) is not int or enable_m not in (0, 1):
        raise ValueError("Invalid M extension configuration")
    overlap = manifest.get("FetchOverlap", 0)
    if type(overlap) is not int or overlap not in (0, 1):
        raise ValueError("Invalid overlapping fetch configuration")
    fast_write = manifest.get("FastDCacheWrite", 0)
    if type(fast_write) is not int or fast_write not in (0, 1):
        raise ValueError("Invalid early D-cache write configuration")
    fast_data = manifest.get("FastDCacheRead", 0)
    if type(fast_data) is not int or fast_data not in (0, 1):
        raise ValueError("Invalid early D-cache read configuration")
    early_data = manifest.get("EarlyDRequest", 0)
    if type(early_data) is not int or early_data not in (0, 1):
        raise ValueError("Invalid EX-stage data request configuration")
    data_overlap = manifest.get("DataOverlap", 0)
    if type(data_overlap) is not int or data_overlap not in (0, 1):
        raise ValueError("Invalid data request overlap configuration")
    btb_bits = manifest.get("BtbIndexBits", 4)
    if type(btb_bits) is not int or not 1 <= btb_bits <= 8:
        raise ValueError("Invalid BTB index width")
    btb_encoding = 0 if btb_bits == 4 else btb_bits
    data_sets, instruction_sets = cache_geometry(manifest)
    instruction_encoding = 0 if instruction_sets == data_sets else instruction_sets
    configuration = (0x0e020000 | (instruction_encoding << 12) | ((fast_write & manifest["CacheEnabled"]) << 19) | (data_overlap << 18) | (btb_encoding << 20) | (early_data << 7) | ((fast_data & manifest["CacheEnabled"]) << 6) | (overlap << 5) | (enable_m << 4) | (manifest["CacheSetBits"] << 8) | manifest["Predictor"] |
                     ((1 - manifest["CacheEnabled"]) << 1) | (manifest["LoadUseBubble"] << 2) |
                     ((manifest["FastICacheHit"] & manifest["CacheEnabled"]) << 3))

    result = parse_result(raw.decode("utf-8-sig"), lut_count=report["resources"]["post_route_luts"],
                          expected_config=configuration, expected_clock_hz=manifest["ClockHz"])
    return {"build": str(build), "uart": str(uart), "manifest": manifest, "report": report,
            "source_snapshot_verified": source_verified,
            "sha256": {**hashes, "uart": sha256(raw).hexdigest()}, "result": result}


def compare(baseline, candidate, variable="FastICacheHit"):
    if variable not in ("FastICacheHit", "FetchOverlap", "FastDCacheRead", "FastDCacheWrite", "EarlyDRequest", "BtbIndexBits", "DataOverlap", "ICacheSetBits", "CacheSetBits"):
        raise ValueError("Unsupported comparison variable")
    if baseline["manifest"].get("EnableM", 0) != candidate["manifest"].get("EnableM", 0):
        raise ValueError("M extension differs in an I-cache-only experiment")
    if variable != "FetchOverlap" and baseline["manifest"].get("FetchOverlap", 0) != candidate["manifest"].get("FetchOverlap", 0):
        raise ValueError("Not an I-cache-hit-only comparison: overlapping fetch differs")
    if variable != "FastICacheHit" and baseline["manifest"]["FastICacheHit"] != candidate["manifest"]["FastICacheHit"]:
        raise ValueError("Early-hit setting differs in an overlapping-fetch-only experiment")
    if variable != "FastDCacheRead" and baseline["manifest"].get("FastDCacheRead", 0) != candidate["manifest"].get("FastDCacheRead", 0):
        raise ValueError("Early D-cache read setting differs in another experiment")
    if variable != "FastDCacheWrite" and baseline["manifest"].get("FastDCacheWrite", 0) != candidate["manifest"].get("FastDCacheWrite", 0):
        raise ValueError("Early D-cache write setting differs in another experiment")
    if variable != "EarlyDRequest" and baseline["manifest"].get("EarlyDRequest", 0) != candidate["manifest"].get("EarlyDRequest", 0):
        raise ValueError("EX-stage data request setting differs in another experiment")
    if variable != "BtbIndexBits" and baseline["manifest"].get("BtbIndexBits", 4) != candidate["manifest"].get("BtbIndexBits", 4):
        raise ValueError("BTB capacity differs in another experiment")
    if variable != "DataOverlap" and baseline["manifest"].get("DataOverlap", 0) != candidate["manifest"].get("DataOverlap", 0):
        raise ValueError("Data request overlap differs in another experiment")
    base_geometry = cache_geometry(baseline["manifest"])
    candidate_geometry = cache_geometry(candidate["manifest"])
    if variable != "ICacheSetBits" and base_geometry[1] != candidate_geometry[1]:
        raise ValueError("Instruction cache geometry differs in another experiment")
    same_sources_verified = baseline.get("source_snapshot_verified", False) and candidate.get("source_snapshot_verified", False)
    if same_sources_verified and {name: value.lower() for name, value in baseline["manifest"]["SourceSnapshot"]["Files"].items()} != {name: value.lower() for name, value in candidate["manifest"]["SourceSnapshot"]["Files"].items()}:
        raise ValueError("RTL/constraint source snapshots differ between cases")
    shared = ("Device", "ClockHz", "ReferenceClockHz", "ClockSource", "UartProfile", "UartBaud",
              "Predictor", "LoadUseBubble", "CacheSetBits", "CacheEnabled")
    for key in shared:
        if key != variable and baseline["manifest"][key] != candidate["manifest"][key]:
            raise ValueError(f"Not a single-variable same-clock comparison: {key}")
    if variable != "BtbIndexBits" and baseline["manifest"]["CacheEnabled"] != 1:
        raise ValueError("The experiment requires enabled caches")
    if variable in ("ICacheSetBits", "CacheSetBits"):
        selected = 1 if variable == "ICacheSetBits" else 0
        if base_geometry[selected] == candidate_geometry[selected]:
            raise ValueError("Cache comparison requires distinct valid widths")
    elif variable == "BtbIndexBits":
        widths = [case["manifest"].get(variable, 4) for case in (baseline, candidate)]
        if any(type(width) is not int or not 1 <= width <= 8 for width in widths) or widths[0] == widths[1]:
            raise ValueError("BTB comparison requires distinct valid index widths")
        if baseline["manifest"]["Predictor"] != 1:
            raise ValueError("BTB comparison requires enabled prediction")
    elif any(type(case["manifest"].get(variable, 0)) is not int for case in (baseline, candidate)) or baseline["manifest"].get(variable, 0) != 0 or candidate["manifest"].get(variable, 0) != 1:
        raise ValueError(f"Expected baseline {variable} off and candidate {variable} on")
    if baseline["sha256"]["FirmwareSha256"] != candidate["sha256"]["FirmwareSha256"]:
        raise ValueError("The firmware must be byte-identical")
    base_result, candidate_result = baseline["result"], candidate["result"]
    for result in (base_result, candidate_result):
        if result["validation_run"] or not result["reportable_duration"] or not result["crc_valid"]:
            raise ValueError("Only validated performance seeds of at least ten seconds can be compared")
    for key in ("iterations", "retired", "seed_crc", "final_crc", "clock_hz"):
        if base_result[key] != candidate_result[key]:
            raise ValueError(f"Workload differs: {key}")
    fields = {"execution_efficiency": "iterations_per_second_per_mhz",
              "resource_efficiency": "iterations_per_second_per_lut",
              "throughput": "iterations_per_second", "cycles": "cycles", "post_route_luts": "lut_count"}
    deltas = {}
    for label, field in fields.items():
        if base_result[field] <= 0 or candidate_result[field] <= 0:
            raise ValueError(f"Nonpositive metric: {field}")
        deltas[label] = {"baseline": base_result[field], "candidate": candidate_result[field],
                         "change_percent": 100 * (candidate_result[field] / base_result[field] - 1)}
    return {"status": "same_firmware_same_clock_comparison_not_physical_limit_proof",
            "variable": variable, "clock_hz": base_result["clock_hz"], "metrics": deltas,
            "same_source_snapshot_verified": same_sources_verified,
            "setup_wns_ns": {"baseline": baseline["report"]["setup_wns_ns"],
                             "candidate": candidate["report"]["setup_wns_ns"]},
            "board_identity_verified_by_this_tool": False, "baseline": baseline, "candidate": candidate}


def main():
    parser = argparse.ArgumentParser(description="Compare one frontend option with byte-identical firmware at the same clock")
    parser.add_argument("--variable", choices=("FastICacheHit", "FetchOverlap", "FastDCacheRead", "FastDCacheWrite", "EarlyDRequest", "BtbIndexBits", "DataOverlap", "ICacheSetBits", "CacheSetBits"), default="FastICacheHit")
    parser.add_argument("--baseline-build", required=True, type=Path)
    parser.add_argument("--candidate-build", required=True, type=Path)
    parser.add_argument("--baseline-uart", required=True, type=Path)
    parser.add_argument("--candidate-uart", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        result = compare(read_case(args.baseline_build, args.baseline_uart), read_case(args.candidate_build, args.candidate_uart), args.variable)
        encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.json:
            with args.json.open("x", encoding="utf-8") as output:
                output.write(encoded)
        print(encoded)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"FAIL paired comparison: {error}\n")


if __name__ == "__main__":
    main()
