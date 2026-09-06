import argparse
import json
from pathlib import Path

from compare_coremark import read_case


def assess(case):
    result = case["result"]
    iterations = result["iterations"]
    cycles = result["cycles"]
    retired = result["retired"]
    frequency = result["clock_hz"]
    luts = case["report"]["resources"]["post_route_luts"]
    for value in (iterations, cycles, retired, frequency, luts):
        if type(value) is not int or value <= 0:
            raise ValueError("Positive integer counters, frequency and physical LUT count are required")
    if frequency != case["manifest"]["ClockHz"] or frequency != case["report"]["clock_hz"]:
        raise ValueError("Firmware, manifest and timing report clocks must agree")
    gates = {
        "clock_exactly_120mhz": frequency == 120000000,
        "execution_at_least_3_coremark_per_mhz": iterations * 1000000 >= 3 * cycles,
        "duration_at_least_ten_seconds": cycles >= 10 * frequency and result["reportable_duration"] is True,
        "performance_seeds": result["validation_run"] is False and result["seed_crc"] == "e9f5",
        "crc_valid": result["crc_valid"] is True,
        "pds_timing_met": case["report"]["constraints_met"] is True and case["manifest"]["TimingConstraintsMet"] is True,
        "target_device": case["manifest"]["Device"] == "PG2L200H-6FBB676",
    }
    efficiency = iterations * 1000000 / cycles
    return {
        "status": "numeric_target_pass" if all(gates.values()) else "target_not_met",
        "gates": gates,
        "target": {"clock_hz": 120000000, "coremark_per_mhz": 3, "coremark": 360},
        "measured": {"clock_hz": frequency, "coremark_per_mhz": efficiency,
                     "hardware_isa": "rv32im" if case["manifest"].get("EnableM", 0) else "rv32i",
                     "nonzero_apm_reported": case["report"]["resources"].get("APM"),
                     "coremark": iterations * frequency / cycles,
                     "coremark_per_lut": iterations * frequency / cycles / luts,
                     "post_route_luts": luts, "cycles_per_iteration": cycles / iterations,
                     "instructions_per_iteration": retired / iterations, "cpi": cycles / retired},
        "diagnostic": {
            "speedup_needed_at_same_clock": 3 / efficiency,
            "cycles_per_iteration_budget": 1000000 / 3,
            "required_average_ipc_with_unchanged_instruction_count": retired * 3 / (iterations * 1000000),
            "single_retire_per_cycle_unchanged_code_upper_bound_coremark_per_mhz": iterations * 1000000 / retired,
            "upper_bound_scope": "Conditional on unchanged retired instruction count and at most one retirement per cycle; not a limit on another compiler or architecture",
        },
        "physical_limits_proven": False,
        "board_identity_verified_by_this_tool": False,
        "scope": "Artifact and numeric gate only; independently retain board capture provenance, repeat runs, validation seeds and electrical checks",
        "evidence": case,
    }


def main():
    parser = argparse.ArgumentParser(description="Enforce the 120 MHz, 3.0 CoreMark/MHz numeric acceptance target")
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--uart", required=True, type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        report = assess(read_case(args.build, args.uart))
        encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.json:
            with args.json.open("x", encoding="utf-8") as output:
                output.write(encoded)
        print(encoded)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Invalid performance evidence: {error}\n")
    if report["status"] != "numeric_target_pass":
        parser.exit(2, "Performance target NOT met; diagnostic report retained.\n")


if __name__ == "__main__":
    main()
