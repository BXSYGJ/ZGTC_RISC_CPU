import argparse
import json
import re
from pathlib import Path


def parse_result(text, allow_short=False, lut_count=None, expected_config=None, expected_clock_hz=27000000):
    def field(pattern, base=10):
        matches = re.findall(pattern, text, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one field: {pattern}")
        return int(matches[0], base)

    iterations = field(r"^Iterations\s+: (\d+)$")
    mode = field(r"^ZGTC COREMARK START iterations=\d+ validation=([01])$")
    initial_iterations = field(r"^ZGTC COREMARK START iterations=(\d+) validation=[01]$")
    size = field(r"^CoreMark Size\s+: (\d+)$")
    seed = field(r"^seedcrc\s+: 0x([0-9a-f]+)$", 16)
    expected = (0x18F2, 0xE3C1, 0x0747, 0x8D84) if mode else (0xE9F5, 0xE714, 0x1FD7, 0x8E3A)
    actual = (seed,) + tuple(field(r"^\[0\]crc" + name + r"\s+: 0x([0-9a-f]+)$", 16) for name in ("list", "matrix", "state"))
    final_crc = field(r"^\[0\]crcfinal\s+: 0x([0-9a-f]+)$", 16)
    if actual != expected:
        raise ValueError(f"CRC mismatch: {actual} != {expected}")
    if size != 666 or iterations < 1 or initial_iterations != iterations or "-DTOTAL_DATA_SIZE=2000" not in text:
        raise ValueError("Invalid standard dataset or iteration metadata")
    cycles = field(r"^ZGTC cycles_hex=([0-9a-f]{16}) retired_hex=[0-9a-f]{16} clock_hz=\d+$", 16)
    retired = field(r"^ZGTC cycles_hex=[0-9a-f]{16} retired_hex=([0-9a-f]{16}) clock_hz=\d+$", 16)
    frequency = field(r"^ZGTC cycles_hex=[0-9a-f]{16} retired_hex=[0-9a-f]{16} clock_hz=(\d+)$")
    ticks = field(r"^Total ticks\s+: (\d+)$")
    seconds_integer = field(r"^Total time \(secs\): (\d+)$")
    if frequency != expected_clock_hz or frequency not in (27000000, 54000000, 60000000, 67500000, 72000000, 75600000, 81000000, 90000000, 99000000, 102600000, 108000000, 120000000, 126000000, 132000000, 135000000, 141750000, 144000000, 146250000, 148500000, 151200000, 157500000, 162000000, 180000000, 194400000, 216000000, 270000000) or cycles <= 0 or retired <= 0:
        raise ValueError("Unsupported frequency or nonpositive counters")
    if ticks != cycles // (frequency // 1000) or seconds_integer != ticks // 1000:
        raise ValueError("Counter and timer report disagree")
    if "ZGTC COREMARK FINISHED" not in text or "ZGTC TRAP" in text or "Cannot validate" in text:
        raise ValueError("Missing normal completion or runtime error")
    short_message = "ERROR! Must execute for at least 10 secs for a valid result!"
    reportable = cycles >= 10 * frequency
    if reportable:
        if "ERROR" in text or "Errors detected" in text or "Correct operation validated." not in text:
            raise ValueError("CoreMark did not validate the complete run")
    elif not allow_short:
        raise ValueError("Run is shorter than ten seconds and cannot be scored")
    elif short_message not in text or "ERROR" in text.replace(short_message, ""):
        raise ValueError("Unexpected short-run errors")
    seconds = cycles / frequency
    result = {"validation_run": bool(mode), "iterations": iterations, "cycles": cycles,
              "retired": retired, "clock_hz": frequency, "seconds": seconds,
              "seed_crc": f"{seed:04x}", "final_crc": f"{final_crc:04x}",
              "crc_valid": True, "reportable_duration": reportable}
    profile_pattern = r"^ZGTC config=([0-9a-f]{8}) ihit=(\d+) imiss=(\d+) dhit=(\d+) dmiss=(\d+) writebacks=(\d+)$"
    profiles = re.findall(profile_pattern, text, re.MULTILINE)
    if "ZGTC config=" in text or expected_config is not None:
        if len(profiles) != 1:
            raise ValueError("Missing or malformed unique performance profile")
        configuration = int(profiles[0][0], 16)
        if expected_config is not None and configuration != expected_config:
            raise ValueError("Runtime hardware configuration differs from requested configuration")
        counters = [int(value) for value in profiles[0][1:]]
        if any(value < 0 or value > 0xFFFFFFFF for value in counters):
            raise ValueError("Cache counter delta exceeds 32-bit range")
        if configuration & 2 and any(counters):
            raise ValueError("Disabled caches must report zero cache counters")
        profile = dict(zip(("i_hits", "i_misses", "d_hits", "d_misses", "writebacks"), counters))
        data_sets = (configuration >> 8) & 15
        instruction_encoding = (configuration >> 12) & 15
        if not 1 <= data_sets <= 8 or instruction_encoding > 10:
            raise ValueError("Invalid cache geometry encoding")
        profile["dcache_set_bits"] = data_sets
        profile["icache_set_bits"] = instruction_encoding or data_sets
        profile["configuration_hex"] = f"{configuration:08x}"
        profile["cache_enabled"] = not bool(configuration & 2)
        profile["predictor_enabled"] = bool(configuration & 1)
        profile["load_use_bubble"] = bool(configuration & 4)
        profile["fast_icache_hit"] = bool(configuration & 8)
        profile["m_extension"] = bool(configuration & 16)
        profile["fetch_overlap"] = bool(configuration & 32)
        profile["fast_dcache_read"] = bool(configuration & 64)
        profile["early_d_request"] = bool(configuration & 128)
        btb_encoding = (configuration >> 20) & 15
        if btb_encoding > 8:
            raise ValueError("Invalid BTB index width encoding")
        profile["btb_index_bits"] = btb_encoding or 4
        profile["data_overlap"] = bool(configuration & (1 << 18))
        profile["fast_dcache_write"] = bool(configuration & (1 << 19))
        if configuration & (1 << 19) and configuration & 2:
            raise ValueError("Early D-cache writes require enabled caches")
        if configuration & 64 and configuration & 2:
            raise ValueError("Early D-cache reads cannot be active with caches disabled")
        if "-march=rv32im" in text and not profile["m_extension"]:
            raise ValueError("RV32IM firmware cannot run on an RV32I-only configuration")
        if configuration & 8 and configuration & 2:
            raise ValueError("Early I-cache response cannot be active with caches disabled")
        profile["interval_includes_counter_read_overhead"] = True
        result["profile"] = profile
    if reportable:
        score = iterations / seconds
        result.update({"iterations_per_second": score, "iterations_per_second_per_mhz": iterations * 1000000 / cycles})
        if lut_count is not None:
            if lut_count <= 0:
                raise ValueError("LUT count must be positive")
            result["iterations_per_second_per_lut"] = score / lut_count
            result["lut_count"] = lut_count
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uart_log", type=Path)
    parser.add_argument("--allow-short", action="store_true")
    parser.add_argument("--luts", type=int)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--expected-config", type=lambda value: int(value, 16))
    parser.add_argument("--clock-hz", type=int, default=27000000)
    args = parser.parse_args()
    result = parse_result(args.uart_log.read_text(encoding="utf-8-sig"), args.allow_short, args.luts, args.expected_config, args.clock_hz)
    encoded = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
