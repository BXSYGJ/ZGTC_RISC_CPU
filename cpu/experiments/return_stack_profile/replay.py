import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
sys.path.insert(0, str(BASE))
from analyze_control import audit as audit_control
from profile_control import file_hash, firmware_image, load_json, require
from load_use_profile import trace_records


def stack_action(instruction):
    opcode = instruction & 127
    destination = (instruction >> 7) & 31
    source = (instruction >> 15) & 31
    destination_link = destination in (1, 5)
    source_link = source in (1, 5)
    if opcode == 111:
        return False, destination_link
    if opcode != 103 or (instruction >> 12) & 7:
        return False, False
    return source_link and (not destination_link or destination != source), destination_link


def replay(event_records, depths=(2, 4, 8, 16)):
    require(depths and len(set(depths)) == len(depths) and all(isinstance(depth, int) and 1 <= depth <= 64 for depth in depths), "Invalid stack depths")
    stacks = {depth: [] for depth in depths}
    metric_names = ("resolved_predictions", "correct_targets", "wrong_targets", "underflows",
                    "resolved_without_prediction", "overflows", "maximum_occupancy")
    statistics = {depth: Counter({name: 0 for name in metric_names}) for depth in depths}
    per_pc = defaultdict(Counter)
    last_targets = {}
    count_names = ("instructions", "hinted_controls", "pop_hints", "push_hints", "pop_then_push_hints",
                   "resolved_pops", "unresolved_final_pop", "pc_last_target_cold", "pc_last_target_changes", "pc_last_target_hits")
    counts = Counter({name: 0 for name in count_names})
    previous = None

    def consume(record, next_pc):
        cycle, address, instruction = record
        require(cycle >= 0 and 0 <= address <= 0xfffffffc and address % 4 == 0, "Invalid committed instruction")
        counts["instructions"] += 1
        pop, push = stack_action(instruction)
        if not pop and not push:
            return
        counts["hinted_controls"] += 1
        counts["pop_hints"] += pop
        counts["push_hints"] += push
        counts["pop_then_push_hints"] += pop and push
        entry = per_pc[address]
        entry["pop_hints"] += pop
        entry["push_hints"] += push
        if pop and next_pc is not None:
            counts["resolved_pops"] += 1
            entry["resolved_pops"] += 1
            if address not in last_targets:
                counts["pc_last_target_cold"] += 1
            elif last_targets[address] != next_pc:
                counts["pc_last_target_changes"] += 1
                entry["pc_last_target_changes"] += 1
            else:
                counts["pc_last_target_hits"] += 1
            last_targets[address] = next_pc
        elif pop:
            counts["unresolved_final_pop"] += 1
        for depth, stack in stacks.items():
            summary = statistics[depth]
            if pop:
                if stack:
                    predicted = stack.pop()
                    if next_pc is not None:
                        summary["resolved_predictions"] += 1
                        summary["correct_targets" if predicted == next_pc else "wrong_targets"] += 1
                        entry[f"depth_{depth}_correct" if predicted == next_pc else f"depth_{depth}_wrong"] += 1
                else:
                    summary["underflows"] += 1
                    if next_pc is not None:
                        summary["resolved_without_prediction"] += 1
            if push:
                if len(stack) == depth:
                    stack.pop(0)
                    summary["overflows"] += 1
                stack.append((address + 4) & 0xffffffff)
            summary["maximum_occupancy"] = max(summary["maximum_occupancy"], len(stack))

    for record in event_records:
        require(len(record) == 3, "Invalid retirement record")
        if previous is not None:
            require(record[0] > previous[0], "Retirement cycles are not strictly increasing")
            consume(previous, record[1])
        previous = record
    require(previous is not None, "Empty retirement trace")
    consume(previous, None)
    for summary in statistics.values():
        require(summary["correct_targets"] + summary["wrong_targets"] == summary["resolved_predictions"], "Target classification lost a return")
        require(summary["resolved_predictions"] + summary["resolved_without_prediction"] == counts["resolved_pops"], "Stack coverage lost a return")
    require(counts["pc_last_target_cold"] + counts["pc_last_target_changes"] + counts["pc_last_target_hits"] == counts["resolved_pops"], "Last-target coverage mismatch")
    return {"scope": "cold committed-instruction return-stack replay; no speculative fetch timing, BTB conflicts, pipeline update lag, or measured cycle savings",
            "counts": dict(counts), "depths": {str(depth): dict(summary) for depth, summary in statistics.items()},
            "return_pcs": [{"pc": address, "pc_hex": f"0x{address:08x}", **dict(entry)} for address, entry in sorted(per_pc.items()) if entry["pop_hints"]]}


def main():
    control = audit_control()
    require(control["counts"]["interrupt_pending_cycles"] == 0, "Interrupt-containing trace needs explicit stack recovery modeling")
    directory = BASE / "build/execution-profile-current"
    report = load_json(directory / "results.json")
    invocation = load_json(directory / "invocation.json")
    for field, filename in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json"), ("invocation_sha256", "invocation.json"), ("uart_sha256", "uart.log"), ("executable_sha256", "objects/Vrv32_soc")):
        require(file_hash(directory / filename) == report[field], "Retirement evidence changed: " + filename)
    require(report["passed"] is True, "Retirement observer did not pass")
    require(file_hash(directory / "firmware.hex") == invocation["firmware_sha256"], "Retirement firmware changed")
    metadata = load_json(directory / "uart.log.retire.json")
    require(metadata == report["metadata"], "Retirement metadata changed")
    result = replay(trace_records(directory / "uart.log.retire.bin", metadata, firmware_image(directory / "firmware.hex")))
    require(result["counts"]["instructions"] == metadata["records"], "Retirement trace incomplete")
    measured = {entry["pc"]: entry for entry in control["control_pcs"]}
    for entry in result["return_pcs"]:
        entry["observed_mem_events"] = measured.get(entry["pc"], {}).get("mem_events", 0)
        entry["observed_mem_flushes"] = measured.get(entry["pc"], {}).get("mem_flushes", 0)
    result.update(schema=1, trace_sha256=report["trace_sha256"], profile_report_sha256=file_hash(directory / "results.json"),
                  control_invocation_sha256=control["invocation_sha256"], analyzer_sha256=file_hash(Path(__file__)),
                  hardware_validated=False, measured_cycle_savings=None,
                  hint_reference="RISC-V Unprivileged RV32I: return-address-stack prediction hints, x1/x5 link registers")
    output = ROOT / "build/return-stack-replay.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
