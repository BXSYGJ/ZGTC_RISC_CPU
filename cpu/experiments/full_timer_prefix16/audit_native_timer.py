import json
import re
from pathlib import Path

import audit_timer_ila as audit

ROOT = Path(__file__).resolve().parent
PARENT_SOURCE = audit.staging.binding()["source"]


def carry_lengths(netlist):
    modules = re.findall(r"\bmodule rv32_peripherals\b(.*?)\bendmodule\b", netlist, re.S)
    audit.require(len(modules) == 1, "Peripheral module missing or ambiguous")
    matches = re.findall(r"\bGTP_LUT6CARRY\s*/\*.*?\*/\s*#\(.*?\)\s*(\S+)\s*\((.*?)\);", modules[0], re.S)
    cells = {}
    outputs = {}
    for name, body in matches:
        audit.require(name not in cells, "Duplicate carry cell")
        ports = re.findall(r"\.(CIN|COUT|Z)\s*\(([^)]*)\)", body)
        audit.require(len(ports) == 3 and len(dict(ports)) == 3, "Missing or duplicated carry ports")
        cells[name] = {port: signal.strip() for port, signal in ports}
        output = cells[name]["COUT"]
        if output:
            audit.require(output not in outputs, "Duplicate carry output driver")
            outputs[output] = name
    lengths = {}
    for name, ports in cells.items():
        match = re.fullmatch(r"timer_incremented\[(\d+)\]", ports["Z"])
        if match is None:
            continue
        bit = int(match[1])
        audit.require(bit not in lengths, "Duplicate timer output driver")
        visited = set()
        current = name
        while current is not None:
            audit.require(current not in visited, "Carry cycle")
            visited.add(current)
            current = outputs.get(cells[current]["CIN"])
        lengths[bit] = len(visited)
    audit.require(set(lengths) == set(range(1, 64)), "Incomplete timer carry outputs")
    return lengths


def audit_native():
    bound = audit.binding()
    parent = Path(PARENT_SOURCE)
    paths = {"parent": parent / "synthesize/pds_soc_top_syn.vm", "candidate": audit.SOURCE / "synthesize/pds_soc_top_syn.vm"}
    lengths = {name: carry_lengths(path.read_text(encoding="utf-8-sig")) for name, path in paths.items()}
    audit.require(lengths["parent"] == {bit: bit for bit in range(1, 64)}, "Unexpected parent timer chain")
    expected = {bit: bit if bit < 16 else bit - 15 if bit < 32 else bit - 31 if bit < 48 else bit - 46 for bit in range(1, 64)}
    audit.require(lengths["candidate"] == expected, "Unexpected candidate timer chain")
    result = {"schema": 1, "scope": "consecutive dedicated CIN/COUT cells feeding timer_incremented; not total logic depth, routed timing or performance",
              "passed": True, "parent_source": str(parent), "candidate_source": str(audit.SOURCE),
              "source_binding": bound, "maximum_consecutive_carry_cells": {name: max(values.values()) for name, values in lengths.items()},
              "per_bit_carry_cells": lengths, "netlist_sha256": {name: audit.digest(path) for name, path in paths.items()},
              "auditor_sha256": audit.digest(Path(__file__)), "hardware_validated": False}
    (ROOT / "build/native-timer-carry-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(audit_native(), indent=2))
