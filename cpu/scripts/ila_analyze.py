import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path

from pds_report import parse_ila_reports, unique_match
from ila_pipeline_minimal_config import DATA_NAMES as MINIMAL_DATA_NAMES, validate_config as validate_minimal_config
from ila_pipeline_platform42_config import PROFILE as PLATFORM42_PROFILE, validate_config as validate_platform42_config


MINIMAL_PROFILE = "RegfileFanout157500Minimal"
COMPACT_PROFILES = (MINIMAL_PROFILE, PLATFORM42_PROFILE)
CANDIDATE_PROFILES = ("Regfile157500Candidate",) + COMPACT_PROFILES


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


PROFILES = {"Legacy27": (27000000, "nt_clk"), "Target120": (120000000, "cpu_clk"),
            "Target132Carry": (132000000, "cpu_clk"), "Target132Kept": (132000000, "cpu_clk"),
            "Regfile157500Candidate": (157500000, "cpu_clk"), MINIMAL_PROFILE: (157500000, "cpu_clk"),
            PLATFORM42_PROFILE: (157500000, "cpu_clk")}
SOURCE_LOCKS = {"Target132Carry": "ila_target132_carry_sources.json",
                "Target132Kept": "ila_target132_kept_sources.json",
                "Regfile157500Candidate": "ila_regfile157500_sources.json",
                MINIMAL_PROFILE: "ila_regfilefanout157500_sources.json",
                PLATFORM42_PROFILE: "ila_regfilefanout157500_sources.json"}


def header_for(profile):
    if profile not in PROFILES:
        raise ValueError("Unknown ILA profile")
    if profile in COMPACT_PROFILES:
        return ["Sample Index"] + list(MINIMAL_DATA_NAMES)
    controls = list(CONTROL_NAMES)
    if profile != "Legacy27":
        controls[10] = "board/soc/core/fetch_complete"
    if profile in SOURCE_LOCKS:
        controls[11] = "board/soc/core/mem_fire"
    return ["Sample Index"] + PC_NAMES + controls


def validate_manifest(path, profile):
    if profile not in PROFILES:
        raise ValueError("Unknown ILA profile")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    clock_hz, clock_net = PROFILES[profile]
    expected = {"Profile": profile, "Device": "PG2L200H-6FBB676", "ClockHz": clock_hz,
                "SampleClockNet": clock_net, "CaptureChannels": 109, "CaptureDepth": 1024,
                "TimingConstraintsMet": True,
                "Channel106Meaning": "fetch_complete" if profile != "Legacy27" else "i_response_valid"}
    if profile in COMPACT_PROFILES:
        del expected["Channel106Meaning"]
        expected.update(CaptureChannels=42, TriggerChannels=33 if profile == MINIMAL_PROFILE else 42,
                        TriggerMatchType=0 if profile == MINIMAL_PROFILE else 1, DataEqualsTrigger=profile == PLATFORM42_PROFILE,
                        Channel39Meaning="mem_flush", Channel40Meaning="fetch_complete", Channel41Meaning="mem_fire")
    elif profile in SOURCE_LOCKS:
        expected["Channel107Meaning"] = "mem_fire"
    for key, value in expected.items():
        if type(manifest.get(key)) is not type(value) or manifest[key] != value:
            raise ValueError("ILA manifest mismatch: " + key)
    artifacts = {
        "BitstreamSha256": "generate_bitstream/pds_soc_top.sbit", "FicSha256": "cpu.fic",
        "SourceAdfSha256": "source.adf", "SourceNetlistSha256": "netlist.v",
        "SourceManifestSha256": "source-manifest.json", "FirmwareSha256": "firmware.hex",
    }
    if profile in CANDIDATE_PROFILES:
        del artifacts["SourceManifestSha256"]
        artifacts["SourceCandidateSha256"] = "source-candidate.json"
    hashes = {}
    for key, relative in artifacts.items():
        actual = hashlib.sha256((path.parent / relative).read_bytes()).hexdigest()
        if not isinstance(manifest.get(key), str) or actual != manifest[key].lower():
            raise ValueError("ILA artifact hash mismatch: " + key)
        hashes[relative] = actual
    fic = (path.parent / "cpu.fic").read_text(encoding="utf-8-sig")
    if profile in COMPACT_PROFILES:
        verification = path.parent / "verify.stdout.txt"
        config_checker = validate_minimal_config if profile == MINIMAL_PROFILE else validate_platform42_config
        config_checker(fic, verification.read_text(encoding="utf-8-sig"))
        hashes["verify.stdout.txt"] = hashlib.sha256(verification.read_bytes()).hexdigest()
    else:
        channels = re.findall(r"^Project\.unit<0>\.triggerChannel<0><(\d+)>=(.+)$", fic, re.MULTILINE)
        if channels != [(str(index), name) for index, name in enumerate(header_for(profile)[1:])]:
            raise ValueError("ILA FIC channel map mismatch")
        for key, value in (("clockChannel", clock_net), ("clockEdge", "Rising"), ("dataDepth", "1024"), ("triggerPortWidth<0>", "109"), ("triggerPortCount", "1"), ("dataEqualsTrigger", "true"), ("enableStorageQualification", "false"), ("enableMultiWindow", "false")):
            values = re.findall(r"^Project\.unit<0>\." + re.escape(key) + r"=(.+)$", fic, re.MULTILINE)
            if values != [value]:
                raise ValueError("ILA FIC property mismatch: " + key)
    source_name = "source-candidate.json" if profile in CANDIDATE_PROFILES else "source-manifest.json"
    original = json.loads((path.parent / source_name).read_text(encoding="utf-8-sig"))
    if original.get("ClockHz") != clock_hz or original.get("FirmwareSha256", "").lower() != manifest["FirmwareSha256"].lower():
        raise ValueError("ILA source manifest clock or firmware mismatch")
    if profile in SOURCE_LOCKS:
        lock = json.loads((Path(__file__).parent / SOURCE_LOCKS[profile]).read_text(encoding="utf-8-sig"))
        snapshot = original.get("SourceSnapshot", {})
        if type(snapshot.get("Schema")) is not int or snapshot["Schema"] != 1 or snapshot.get("Files") != lock or len(lock) != 20:
            raise ValueError("ILA source revision requires " + profile + " remapping")
        required = {"Device": "PG2L200H-6FBB676", "ClockHz": 132000000, "TimingConstraintsMet": True,
                    "CacheEnabled": 1, "Predictor": 1, "UartProfile": "RemoteLab", "UartBaud": 115200,
                    "EnableM": 1, "FetchOverlap": 1, "FastDCacheRead": 1, "FastDCacheWrite": 1,
                    "ICacheSetBits": 8, "CacheSetBits": 6, "EarlyDRequest": 1, "BtbIndexBits": 8,
                    "DataOverlap": 1, "FastICacheHit": 1, "LoadUseBubble": 0}
        if profile in CANDIDATE_PROFILES:
            required = {"Schema": 1, "Profile": profile, "Device": "PG2L200H-6FBB676", "ClockHz": 157500000,
                        "UartProfile": "RemoteLab", "UartBaud": 115200, "SourceTimingConstraintsMet": False,
                        "SourceAcceptedManifest": False, "FullScoreQualified": False, "HardwareValidated": False,
                        "Scope": "audited_synthesis_input_for_independent_ILA_implementation_not_timing_or_score_qualification"}
            for key in ("SourceTimingConstraintsMet", "SourceAcceptedManifest"):
                if manifest.get(key) is not False:
                    raise ValueError("ILA failed source qualification flag changed: " + key)
            if manifest.get("SourceSnapshot") != snapshot:
                raise ValueError("ILA copied source snapshot mismatch")
            for key in ("SourceAdfSha256", "SourceNetlistSha256", "FirmwareSha256"):
                if original.get(key, "").lower() != manifest[key].lower():
                    raise ValueError("ILA source candidate artifact mismatch: " + key)
            for key, value in (("triggerMatchType<0>", "0" if profile == MINIMAL_PROFILE else "1"), ("triggerMatchCount<0>", "1"), ("triggerMatchCountWidth<0>", "0")):
                if re.findall(r"^Project\.unit<0>\." + re.escape(key) + r"=(.+)$", fic, re.MULTILINE) != [value]:
                    raise ValueError("ILA regfile trigger property mismatch: " + key)
        for key, value in required.items():
            if type(original.get(key)) is not type(value) or original[key] != value:
                raise ValueError("ILA source configuration mismatch: " + key)
    timing_path = path.parent / "report_timing/pds_soc_top.rtr"
    timing = timing_path.read_text(encoding="utf-8-sig")
    summary = unique_match(r"Design Summary\s*:\s*([^\r\n]+)", timing, "ILA timing summary").group(1).strip()
    if summary != "All Constraints Met.":
        raise ValueError("ILA original timing report is not passing")
    clock_name = "clk" if profile == "Legacy27" else "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred"
    kind = "Declared" if profile == "Legacy27" else r"Generated \(clk\)"
    clock = unique_match(r"^\s*" + re.escape(clock_name) + r"\s+([0-9.]+)\s+\{[^}]+\}\s+" + kind + r"\s+(\d+)", timing, "ILA CPU clock", re.MULTILINE)
    if abs(float(clock.group(1)) - 1e9 / clock_hz) > 0.005 or int(clock.group(2)) < 1:
        raise ValueError("ILA timing report CPU period or loads mismatch")
    performance = unique_match(re.escape(clock_name) + r"\s+([0-9.]+) MHz\s+([0-9.]+) MHz\s+([0-9.]+)\s+([0-9.]+)\s+(-?[0-9.]+)", timing, "ILA CPU performance")
    if float(performance.group(5)) < 0 or abs(float(performance.group(3)) - 1e9 / clock_hz) > 0.005:
        raise ValueError("ILA CPU performance summary contradicts timing")
    hashes["report_timing/pds_soc_top.rtr"] = hashlib.sha256(timing_path.read_bytes()).hexdigest()
    result = {"profile": profile, "artifacts_sha256": hashes, "hardware_origin_verified_by_analyzer": False}
    if profile in CANDIDATE_PROFILES:
        log_path = path.parent / "run.log"
        physical = parse_ila_reports(timing, log_path.read_text(encoding="utf-8-sig"), clock_hz)
        if not physical["constraints_met"]:
            raise ValueError("ILA original full timing and resource report rejected")
        hashes["run.log"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
        result["physical_summary"] = physical
        result["score_qualification_verified_by_analyzer"] = False
    return result


def read_capture(path, profile="Legacy27"):
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.reader(source))
    if not rows or rows[0] != header_for(profile):
        raise ValueError("CSV header does not match the verified profile FIC")
    if len(rows) != 1025:
        raise ValueError("Expected exactly 1024 captured samples")
    result = []
    for index, row in enumerate(rows[1:]):
        if len(row) != len(header_for(profile)) or row[0] != str(index) or any(value not in ("0", "1") for value in row[1:]):
            raise ValueError(f"Invalid sample order, width or binary data at {index}")
        bits = [int(value) for value in row[1:]]
        if profile in COMPACT_PROFILES:
            decoded = {"ex_pc": sum(bits[bit] << bit for bit in range(32))}
            decoded.update(zip(("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid",
                                "id_fire", "ex_fire", "mem_flush", "fetch_complete", "mem_fire"), bits[32:]))
        else:
            decoded = {f"{stage}_pc": sum(bits[offset + bit] << bit for bit in range(32))
                       for stage, offset in (("ex", 0), ("id", 32), ("if", 64))}
            decoded.update(zip(("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid",
                                "id_fire", "ex_fire", "mem_sent", "mem_load", "redirect",
                                "fetch_complete" if profile != "Legacy27" else "i_response",
                                "mem_fire" if profile in SOURCE_LOCKS else "d_response", "i_command"), bits[96:]))
        if (decoded["id_fire"] and not decoded["id_valid"]) or (decoded["ex_fire"] and not decoded["ex_valid"]):
            raise ValueError("Pipeline fire/valid invariant violated; check signal mapping")
        if profile in SOURCE_LOCKS and decoded["mem_fire"] and not decoded["mem_valid"]:
            raise ValueError("MEM fire/valid invariant violated; check signal mapping")
        result.append(decoded)
    for previous, following in zip(result, result[1:]):
        if previous["id_fire"] and (not following["ex_valid"] or
                                    (profile not in COMPACT_PROFILES and following["ex_pc"] != previous["id_pc"])):
            raise ValueError("ID-to-EX transfer mismatch across adjacent samples")
        if previous["ex_fire"] and not following["mem_valid"]:
            raise ValueError("EX-to-MEM valid transfer mismatch across adjacent samples")
        if profile in SOURCE_LOCKS and following["wb_valid"] and not previous["mem_fire"]:
            raise ValueError("MEM-to-WB transfer mismatch across adjacent samples")
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


def summarize(samples, symbols, profile="Legacy27"):
    if profile not in PROFILES:
        raise ValueError("Unknown ILA profile")
    clock_hz = PROFILES[profile][0]
    count = len(samples)
    executed = Counter(function_at(sample["ex_pc"], symbols) for sample in samples if sample["ex_fire"])
    result = {
        "samples": count, "profile": profile, "clock_hz": clock_hz, "window_us": count * 1e6 / clock_hz,
        "first_to_last_us": (count - 1) * 1e6 / clock_hz,
        "temporal_pairs_checked": count - 1,
        "wb_events": sum(sample["wb_valid"] for sample in samples),
        "window_wb_per_cycle": sum(sample["wb_valid"] for sample in samples) / count,
        "stage_occupied_cycles": {stage: sum(sample[f"{stage}_valid"] for sample in samples)
                                  for stage in ("if", "id", "ex", "mem", "wb")},
        "id_held_cycles": sum(sample["id_valid"] and not sample["id_fire"] for sample in samples),
        "ex_held_cycles": sum(sample["ex_valid"] and not sample["ex_fire"] for sample in samples),
        "ex_fire_function_counts": dict(executed.most_common()),
    }
    if profile in COMPACT_PROFILES:
        result.update(mem_held_cycles=sum(sample["mem_valid"] and not sample["mem_fire"] for sample in samples),
                      mem_flush_cycles=sum(sample["mem_flush"] for sample in samples),
                      fetch_complete_events=sum(sample["fetch_complete"] for sample in samples),
                      window_cycles_per_wb_event=count / result["wb_events"] if result["wb_events"] else None,
                      unavailable_metrics=["IF_PC", "ID_PC", "load_wait_cause", "early_redirect_count", "global_CoreMark_IPC"],
                      scope="local_capture_window_only_not_global_performance_or_hazard_attribution")
    else:
        label = ("mem_load_sent_without_mem_fire_cycles" if profile in SOURCE_LOCKS else
                 "mem_load_sent_without_cache_response_cycles" if profile == "Target120" else "load_response_wait_cycles")
        result[label] = sum(sample["mem_valid"] and sample["mem_load"] and sample["mem_sent"] and
                            not sample["mem_fire" if profile in SOURCE_LOCKS else "d_response"] for sample in samples)
        result["redirect_cycles"] = sum(sample["redirect"] for sample in samples)
        result["i_command_high_cycles"] = sum(sample["i_command"] for sample in samples)
    return result



def render_svg(samples, title, start=0, length=128, profile="Legacy27"):
    if profile not in PROFILES:
        raise ValueError("Unknown ILA profile")
    clock_mhz = PROFILES[profile][0] / 1e6
    if start < 0 or length < 2 or start + length > len(samples):
        raise ValueError("Invalid waveform display window")
    signals = ("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid", "id_fire", "ex_fire", "mem_sent",
               "mem_fire" if profile in SOURCE_LOCKS else "d_response", "redirect")
    if profile in COMPACT_PROFILES:
        signals = ("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid", "id_fire", "ex_fire",
                   "mem_fire", "mem_flush", "fetch_complete")
    parts = ["<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1400\" height=\"700\" viewBox=\"0 0 1400 700\">",
             "<rect width=\"1400\" height=\"700\" fill=\"#0b1324\"/>",
             "<g fill=\"#e2e8f0\" font-family=\"Arial, sans-serif\">",
             f"<text x=\"24\" y=\"32\" font-size=\"20\">{html.escape(title)}</text>",
             f"<text x=\"24\" y=\"58\" font-size=\"14\">ILA signal data | {clock_mhz:g} MHz | samples {start}..{start+length-1} | one sample per CPU clock</text>"]
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
    if profile in COMPACT_PROFILES:
        parts.append('<text x="20" y="610" font-size="14">EX_PC</text>')
        window = samples[start:start+length]
        run_start = 0
        for boundary in range(1, length + 1):
            if boundary < length and (window[boundary]["ex_pc"], window[boundary]["ex_valid"]) == (window[run_start]["ex_pc"], window[run_start]["ex_valid"]):
                continue
            left = 170 + run_start * 1184 / length
            right = 170 + boundary * 1184 / length
            active = window[run_start]["ex_valid"]
            color = "#fbbf24" if active else "#64748b"
            parts.append(f'<path d="M{left:.3f} 609L{left+3:.3f} 596H{right-3:.3f}L{right:.3f} 609L{right-3:.3f} 622H{left+3:.3f}Z" stroke="{color}" fill="none"/>')
            if right - left >= 66:
                label = f'{window[run_start]["ex_pc"]:08x}' if active else "invalid"
                parts.append(f'<text x="{(left+right)/2:.3f}" y="613" font-family="monospace" font-size="12" text-anchor="middle">{label}</text>')
            run_start = boundary
    parts += ["<text x=\"24\" y=\"683\" font-size=\"13\">Local window only; occupied/held cycles are not automatically data hazards or global IPC.</text>", "</g></svg>"]
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="Legacy27")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.profile != "Legacy27" and args.manifest is None:
        parser.error(args.profile + " analysis requires the matching ILA --manifest")
    provenance = validate_manifest(args.manifest, args.profile) if args.manifest else None
    symbols = read_symbols(args.symbols)
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for path in args.captures:
        samples = read_capture(path, args.profile)
        result = summarize(samples, symbols, args.profile)
        result["capture_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        result["symbols_sha256"] = hashlib.sha256(args.symbols.read_bytes()).hexdigest()
        result["artifact_verification"] = provenance
        result["source"] = path.name
        results.append(result)
        (args.output / f"{path.stem}.svg").write_text(render_svg(samples, path.stem, profile=args.profile), encoding="utf-8")
        with (args.output / f"{path.stem}-decoded.csv").open("w", newline="", encoding="utf-8-sig") as output:
            writer = csv.DictWriter(output, fieldnames=list(samples[0]))
            writer.writeheader()
            writer.writerows(samples)
    (args.output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
