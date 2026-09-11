import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
sys.path.insert(0, str(BASE.parents[1] / "scripts"))
from load_use_profile import file_hash, firmware_image, load_json, require, trace_records


def replay(records, index_bits=8):
    require(1 <= index_bits <= 8, "Unsupported index width")
    mask = (1 << index_bits) - 1
    rotation = 4 % index_bits
    direct = {}
    paired = {}
    unique = set()
    replacements = Counter()
    controls = 0
    direct_cold = 0
    two_way_misses = 0
    for cycle, address, instruction in records:
        if instruction & 127 not in (99, 103, 111):
            continue
        require(address < 65536 and address >= 0 and address % 4 == 0, "Control PC outside bounded hardware address space")
        controls += 1
        unique.add(address)
        upper = (address >> (index_bits + 2)) & mask
        index = ((address >> 2) ^ ((upper << rotation) | (upper >> (index_bits - rotation)))) & mask
        previous = direct.get(index)
        if previous != address:
            if previous is None:
                direct_cold += 1
            else:
                replacements[address] += 1
            direct[index] = address
        location = index & (mask >> 1)
        entries = paired.setdefault(location, [])
        if address in entries:
            entries.remove(address)
        else:
            two_way_misses += 1
            if len(entries) == 2:
                entries.pop()
        entries.insert(0, address)
    return {"scope": "cold committed-control-PC replay; not actual fetch misses, direction prediction or CoreMark performance",
            "controls": controls, "unique_control_pcs": len(unique), "direct_cold_allocations": direct_cold,
            "direct_replacements": sum(replacements.values()), "direct_total_allocations": direct_cold + sum(replacements.values()),
            "two_way_total_allocations": two_way_misses,
            "top_direct_replacements": [{"pc_hex": f"0x{address:08x}", "count": count} for address, count in replacements.most_common(12)]}


def main():
    directory = BASE / "build/execution-profile-current"
    report = load_json(directory / "results.json")
    for field, filename in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json"), ("invocation_sha256", "invocation.json")):
        require(file_hash(directory / filename) == report[field], "Retirement evidence changed")
    invocation = load_json(directory / "invocation.json")
    require(file_hash(directory / "firmware.hex") == invocation["firmware_sha256"], "Retirement firmware changed")
    metadata = load_json(directory / "uart.log.retire.json")
    result = replay(trace_records(directory / "uart.log.retire.bin", metadata, firmware_image(directory / "firmware.hex")))
    result.update(trace_sha256=report["trace_sha256"], profile_report_sha256=file_hash(directory / "results.json"),
                  replay_source_sha256=file_hash(Path(__file__)), hardware_validated=False)
    output = ROOT / "build/conflict-replay.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
