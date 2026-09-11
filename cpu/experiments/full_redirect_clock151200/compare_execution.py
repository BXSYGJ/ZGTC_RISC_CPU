import json
import sys
from collections import Counter
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
from load_use_profile import DRIVER_SHA256, file_hash, firmware_image, load_json, require, trace_records
from audit_short import read_run


def compare_records(reference, candidate):
    previous_reference = None
    previous_candidate = None
    count = 0
    reference_cycles = 0
    candidate_cycles = 0
    changed = Counter()
    saved_by_previous_opcode = Counter()
    transitions = {}
    for before, after in zip_longest(reference, candidate):
        require(before is not None and after is not None, "Retirement trace lengths differ")
        require(before[1:] == after[1:], "Retired PC or instruction sequence differs")
        if previous_reference is not None:
            before_gap = before[0] - previous_reference[0]
            after_gap = after[0] - previous_candidate[0]
            require(before_gap > 0 and after_gap > 0, "Non-increasing retirement cycles")
            saved = before_gap - after_gap
            reference_cycles += before_gap
            candidate_cycles += after_gap
            category = "improved" if saved > 0 else "worsened" if saved < 0 else "unchanged"
            changed[category] += 1
            opcode = previous_reference[2] & 127
            saved_by_previous_opcode[f"0x{opcode:02x}"] += saved
            transition = (previous_reference[1], before[1])
            item = transitions.setdefault(transition, {"previous_pc": transition[0], "next_pc": transition[1], "previous_instruction": previous_reference[2], "count": 0, "reference_extra_cycles": 0, "candidate_extra_cycles": 0, "saved_cycles": 0})
            item["count"] += 1
            item["reference_extra_cycles"] += before_gap - 1
            item["candidate_extra_cycles"] += after_gap - 1
            item["saved_cycles"] += saved
        previous_reference, previous_candidate = before, after
        count += 1
    require(count >= 2, "Trace must contain both timer boundaries")
    require(sum(changed.values()) == count - 1, "Interval count not conserved")
    require(sum(saved_by_previous_opcode.values()) == reference_cycles - candidate_cycles, "Saved cycles not conserved")
    ordered = sorted(transitions.values(), key=lambda item: (-item["candidate_extra_cycles"], item["previous_pc"], item["next_pc"]))
    return {"records": count, "reference_cycles": reference_cycles, "candidate_cycles": candidate_cycles,
            "saved_cycles": reference_cycles - candidate_cycles, "interval_changes": dict(changed),
            "saved_cycles_by_previous_opcode": dict(saved_by_previous_opcode), "transitions": ordered}


def verified_profile(project, short_id):
    directory = project / "build/execution-profile-current"
    report = load_json(directory / "results.json")
    for field, name in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json"),
                        ("executable_sha256", "objects/Vrv32_soc"), ("uart_sha256", "uart.log"), ("invocation_sha256", "invocation.json")):
        require(file_hash(directory / name) == report[field], "Changed profile artifact: " + name)
    invocation = load_json(directory / "invocation.json")
    require(invocation["runner_sha256"] == file_hash(project / "profile_execution.py"), "Changed profile runner")
    short = project / "build/compiled" / short_id
    manifest, result = read_run(short)
    require(file_hash(short / "manifest.json") == invocation["baseline_manifest_sha256"], "Wrong original short run")
    require(report["passed"] is True and report["result"] == result, "Observer differs from original result")
    require((directory / "uart.log").read_bytes() == (short / "coremark.sim.uart").read_bytes(), "Observer changed UART")
    require(file_hash(directory / "firmware.hex") == invocation["firmware_sha256"] == manifest["FirmwareSha256"], "Wrong observed firmware")
    expected = dict(manifest["SourceSnapshot"], **{"sim/coremark_compiled.cpp": DRIVER_SHA256})
    require(invocation["inputs"] == expected, "Unexpected observer input set")
    for relative, value in expected.items():
        require(file_hash(directory / "source" / relative) == value, "Changed observed source: " + relative)
        if relative != "sim/coremark_compiled.cpp":
            require(file_hash(project / relative) == value, "Current source changed: " + relative)
    metadata = load_json(directory / "uart.log.retire.json")
    require(metadata == report["metadata"] and metadata["cycles"] == result["cycles"], "Wrong profile boundaries")
    records = trace_records(directory / "uart.log.retire.bin", metadata, firmware_image(directory / "firmware.hex"))
    return records, report, invocation


def main():
    parent = ROOT.parent / "full_control_commit"
    before, reference, before_invocation = verified_profile(parent, "20260910-195856-6bf511dd")
    after, candidate, after_invocation = verified_profile(ROOT, "20260910-233631-e15b5716")
    require(before_invocation["boundaries"] == after_invocation["boundaries"], "Timer PCs differ")
    changed = {name for name in before_invocation["inputs"] if before_invocation["inputs"][name] != after_invocation["inputs"].get(name)}
    require(changed == {"rtl/rv32_core.sv"}, "Unexpected observed RTL changes")
    delta = load_json(ROOT.parent / "full_redirect_prime/source-inputs.json")
    reconstructed = (parent / "rtl/rv32_core.sv").read_text(encoding="utf-8")
    for old, new in delta["substitutions"]:
        require(reconstructed.count(old) == 1, "Ambiguous CPU substitution")
        reconstructed = reconstructed.replace(old, new)
    require(reconstructed == (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8"), "Unexpected CPU change")
    summary = compare_records(before, after)
    require(summary["records"] == reference["records"] == candidate["records"], "Wrong record totals")
    require(summary["reference_cycles"] == reference["result"]["cycles"] and summary["candidate_cycles"] == candidate["result"]["cycles"], "Wrong timed interval totals")
    summary.update({"scope": "paired timer-bounded RTL retirement intervals, not stall causality or a long-run score",
                    "reference_report_sha256": file_hash(parent / "build/execution-profile-current/results.json"),
                    "candidate_report_sha256": file_hash(ROOT / "build/execution-profile-current/results.json"),
                    "analyzer_sha256": file_hash(Path(__file__)), "hardware_validated": False})
    destination = ROOT / "build/execution-profile-current/paired-comparison.json"
    text = json.dumps(summary, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite changed profile comparison")
    destination.write_text(text, encoding="utf-8")
    print(json.dumps(dict(summary, transitions=summary["transitions"][:12]), indent=2))


if __name__ == "__main__":
    main()
