import json
import struct
from collections import Counter, defaultdict

from profile_control import ROOT, SHORT, OUTPUT, REFERENCE, FLAGS, DRIVER_SHA256, observe_soc, observe_driver
from profile_control import file_hash, load_json, require, firmware_image, verified_build, check_simulation_result

RECORD = struct.Struct("<QIII")
BITS = {name: 1 << index for index, name in enumerate(FLAGS)}


def bit(flags, name):
    return bool(flags & BITS[name])


def records(path):
    with path.open("rb") as source:
        while True:
            block = source.read(RECORD.size * 65536)
            if not block:
                return
            require(len(block) % RECORD.size == 0, "Truncated control record")
            yield from RECORD.iter_unpack(block)


def classify_ex_block(flags):
    if not bit(flags, "ex_valid") or bit(flags, "ex_fire"):
        return None
    if bit(flags, "interrupt_pending"):
        return "interrupt_drain"
    if bit(flags, "mem_flush"):
        return "older_flush"
    if not bit(flags, "mem_ready"):
        return "memory_stage_not_ready"
    if bit(flags, "load_use_wait"):
        return "load_use_wait"
    if bit(flags, "ex_serial") and (bit(flags, "mem_valid") or bit(flags, "wb_valid")):
        return "serial_drain"
    if bit(flags, "ex_muldiv") and not bit(flags, "muldiv_valid"):
        return "muldiv_result_wait"
    return "unclassified"


def summarize(event_records, metadata, image):
    counts = Counter()
    stalls = Counter()
    branches = defaultdict(Counter)
    previous = None
    for index, (cycle, ex_pc, mem_pc, flags) in enumerate(event_records):
        require(cycle == metadata["start_cycle"] + index, "Control cycle missing, duplicated or reordered")
        require(cycle < metadata["stop_cycle"], "Control cycle outside timed interval")
        require(not bit(flags, "ex_fire") or bit(flags, "ex_valid"), "EX fire without valid")
        require(not bit(flags, "mem_fire") or bit(flags, "mem_valid"), "MEM fire without valid")
        require(bit(flags, "frontend_flush") == (bit(flags, "mem_flush") or bit(flags, "ex_redirect")), "Frontend flush identity failed")
        if previous is not None:
            require(not bit(flags, "wb_valid") or bit(previous, "mem_fire"), "WB event lacks prior MEM fire")
        previous = flags
        counts["cycles"] += 1
        counts["wb_events"] += bit(flags, "wb_valid")
        counts["wb_empty_cycles"] += not bit(flags, "wb_valid")
        counts["ex_empty_cycles"] += not bit(flags, "ex_valid")
        counts["ex_fire_events"] += bit(flags, "ex_fire")
        counts["early_redirects"] += bit(flags, "ex_redirect")
        counts["mem_flushes"] += bit(flags, "mem_flush")
        counts["interrupt_pending_cycles"] += bit(flags, "interrupt_pending")
        counts["redirect_prediction_pending_cycles"] += bit(flags, "fetch_redirect_pending")
        reason = classify_ex_block(flags)
        if reason is not None:
            stalls[reason] += 1
        control_kind = next((kind for kind in ("branch", "jal", "jalr") if bit(flags, "ex_decode.is_" + kind)), None)
        if bit(flags, "ex_fire") and control_kind is not None:
            require(ex_pc % 4 == 0 and ex_pc + 4 <= len(image), "EX control PC outside firmware")
            opcode = int.from_bytes(image[ex_pc:ex_pc + 4], "little") & 127
            require(opcode == {"branch": 99, "jal": 111, "jalr": 103}[control_kind], "EX control type differs from actual firmware")
            entry = branches[ex_pc]
            entry["ex_events"] += 1
            entry["early_redirects"] += bit(flags, "ex_redirect")
            entry["load_dependent_ex_events"] += bit(flags, "early_load_dependency")
        if bit(flags, "mem_fire") and bit(flags, "mem_branch"):
            entry = branches[mem_pc]
            entry["mem_events"] += 1
            entry["mem_flushes"] += bit(flags, "mem_flush")
            entry["already_early_redirected"] += bit(flags, "mem_early_redirect")
            entry["conditional_mem_events"] += bit(flags, "mem_conditional")
    require(counts["cycles"] == metadata["cycles"] == metadata["stop_cycle"] - metadata["start_cycle"], "Incomplete timed control interval")
    require(counts["wb_events"] == metadata["records"] - 1, "Control WB count differs from retirement interval")
    require(counts["wb_empty_cycles"] == metadata["cycles"] - metadata["records"] + 1, "WB bubble count does not conserve retirement gaps")
    require(counts["ex_empty_cycles"] + counts["ex_fire_events"] + sum(stalls.values()) == counts["cycles"], "EX state partition does not conserve cycles")
    by_pc = []
    for address, values in branches.items():
        item = {"pc": address, "pc_hex": f"0x{address:08x}", "instruction_hex": image[address:address + 4][::-1].hex(), **dict(values)}
        item["redirect_events"] = item.get("early_redirects", 0) + item.get("mem_flushes", 0)
        by_pc.append(item)
    return {"counts": dict(counts), "ex_blocked_priority_partition": dict(stalls),
            "control_pcs": sorted(by_pc, key=lambda item: (-item["redirect_events"], item["pc"])),
            "scope": "observed control events and overlapping conditions; blocked partition follows explicit priority, not additive causal cycle savings"}


def audit():
    invocation = load_json(OUTPUT / "invocation.json")
    manifest, expected_result = verified_build(SHORT)
    require(invocation["passed"] is True and invocation["flags"] == list(FLAGS), "Incomplete control observation or changed bit order")
    require(invocation["record_bytes"] == RECORD.size and invocation["baseline_manifest_sha256"] == file_hash(SHORT / "manifest.json"), "Wrong control record or base manifest")
    require(invocation["runner_sha256"] == file_hash(ROOT / "profile_control.py") == file_hash(OUTPUT / "generator-original.py"), "Control observer generator changed")
    require(set(invocation["inputs"]) == set(manifest["SourceSnapshot"]), "Incomplete control source inventory")
    observer = ROOT.parents[1] / "build/load-use-profile-stage/sim/coremark_compiled.cpp"
    require(file_hash(observer) == DRIVER_SHA256, "Original retirement observer changed")
    for relative, expected in invocation["inputs"].items():
        require(file_hash(OUTPUT / "source" / relative) == expected, "Control captured input changed: " + relative)
        require(file_hash(ROOT / relative) == manifest["SourceSnapshot"][relative], "Current original source changed: " + relative)
        if relative == "rtl/rv32_soc.sv":
            require((OUTPUT / "source" / relative).read_text() == observe_soc((SHORT / "source" / relative).read_text()), "Observer altered functional SoC logic")
        elif relative == "sim/coremark_compiled.cpp":
            require((OUTPUT / "source" / relative).read_text() == observe_driver(observer.read_text()), "Control driver instrumentation changed")
        else:
            require(expected == manifest["SourceSnapshot"][relative], "Observer modified non-observation source")
    require(invocation["compile_command"] == [argument.replace(str(SHORT), str(OUTPUT)) for argument in manifest["CompileCommand"]], "Control compile parameters changed")
    require(set(invocation["outputs"]) == {"objects/Vrv32_soc", "uart.log", "uart.log.retire.bin", "uart.log.retire.json", "uart.log.control.bin", "compile.log", "execute.log"}, "Incomplete control output inventory")
    for filename, expected in invocation["outputs"].items():
        require(file_hash(OUTPUT / filename) == expected, "Control output changed: " + filename)
    require(file_hash(OUTPUT / "firmware.hex") == invocation["firmware_sha256"] == manifest["FirmwareSha256"], "Control firmware changed")
    metadata = load_json(OUTPUT / "uart.log.retire.json")
    require(metadata == invocation["metadata"] and metadata["cycles"] == expected_result["cycles"], "Wrong control time boundaries")
    require((OUTPUT / "uart.log").read_bytes() == (SHORT / "coremark.sim.uart").read_bytes(), "Control UART changed")
    require(check_simulation_result((OUTPUT / "uart.log").read_text(), manifest["FirmwareBuild"], manifest["HardwareParameters"], True) == expected_result == invocation["result"], "Control observation changed benchmark result")
    for filename in ("uart.log.retire.bin", "uart.log.retire.json"):
        require(file_hash(OUTPUT / filename) == file_hash(REFERENCE / filename), "Control observation changed original retirement trace")
    summary = summarize(records(OUTPUT / "uart.log.control.bin"), metadata, firmware_image(OUTPUT / "firmware.hex"))
    summary.update(schema=1, invocation_sha256=file_hash(OUTPUT / "invocation.json"), analyzer_sha256=file_hash(ROOT / "analyze_control.py"), hardware_validated=False)
    (OUTPUT / "analysis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    result = audit()
    print(json.dumps({"counts": result["counts"], "ex_blocked_priority_partition": result["ex_blocked_priority_partition"], "top_control_pcs": result["control_pcs"][:12]}, indent=2))
