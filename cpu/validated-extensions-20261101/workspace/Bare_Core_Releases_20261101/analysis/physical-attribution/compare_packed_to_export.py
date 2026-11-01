"""Locate packed FFs absent from the final simulation export, without LUT weights."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def compare(native_path, export_inventory):
    lines = native_path.read_text(encoding="utf-8-sig").splitlines()
    native = {}
    for index, line in enumerate(lines):
        if line == "Inst":
            name, kind = lines[index + 1].split(";", 1)
            pins = []
            cursor = index + 3
            while cursor < len(lines) and lines[cursor]:
                pin, direction = lines[cursor].split(";", 1)
                if direction == "2" and re.search(r"Q$", pin):
                    pins.append(pin)
                cursor += 1
            if kind == "gopSRL2":
                pins = ["SRL_FF0", "SRL_FF1"]
            native[name] = {"kind": kind, "ff_outputs": pins, "ff_count": len(pins)}
    exported = Counter()
    for cell in export_inventory["cells"]:
        if cell["resource"] == "FF":
            parent = cell["provenance"].rsplit("/", 2)[0]
            exported[parent] += 1
    differences = []
    for name, node in native.items():
        if node["ff_count"] != exported[name]:
            differences.append({"packed_instance": name, "packed_kind": node["kind"],
                                "packed_ff_outputs": node["ff_outputs"], "packed_ff_count": node["ff_count"],
                                "exported_ff_count": exported[name]})
    unmatched = {name: count for name, count in exported.items() if name not in native}
    return {"native_ff_count": sum(node["ff_count"] for node in native.values()),
            "exported_ff_count": sum(exported.values()), "differences": differences, "unmatched_exported_owners": unmatched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("native", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = compare(args.native, json.loads(args.inventory.read_text(encoding="utf-8-sig")))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
