import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re


def inspect_netlist(text, limit=None, register_prefix="request_address"):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", register_prefix):
        raise ValueError("Invalid register prefix")
    reports = {}
    modules = re.findall(r"^module\s+(\S+)(.*?)^endmodule", text, re.M | re.S)
    for name, body in modules:
        if not re.fullmatch(r"rv32_cache(?:_\d+)?", name):
            continue
        if name in reports:
            raise ValueError("Duplicate native cache module")
        pins = Counter()
        for expression in re.findall(r"\.\w+\s*\(([^()]*)\)", body):
            pins.update(re.findall(r"\\[^\s,{}]+|[A-Za-z_][A-Za-z0-9_$]*(?:\[\d+\])?", expression))
        pattern = (r"(?:\(\*([^\r\n]*?)\*\)\s*)?GTP_DFF_CE\s*/\*\s*"
                   r"(\\" + re.escape(register_prefix) + r"[^\s]*?)\s*\*/\s*#\((.*?)\)\s+"
                   r"\\[^\s]+\s*\((.*?)\);")
        groups = defaultdict(list)
        for attributes, label, parameters, connections in re.findall(pattern, body, re.S):
            bit = re.search(r"\[(\d+)\]", label)
            if bit is None:
                raise ValueError("Address register label has no bit index")
            pairs = re.findall(r"\.(\w+)\s*\(([^()]*)\)", connections)
            ports = {port: value.strip() for port, value in pairs}
            if len(ports) != len(pairs) or set(ports) != {"Q", "C", "CE", "CLK", "D"}:
                raise ValueError("Unsupported or duplicate address register ports")
            native = re.search(r"\bPAP_MAX_FANOUT\s*=\s*(\d+)\b", attributes)
            uses = pins[ports["Q"]] - 1
            if uses < 0:
                raise ValueError("Missing address output pin")
            groups[int(bit.group(1))].append({
                "label": label, "ports": ports,
                "parameters": re.sub(r"\s+", "", parameters),
                "native_max_fanout": int(native.group(1)) if native else None,
                "direct_sink_pin_occurrences": uses,
            })
        if not groups:
            raise ValueError("No address registers in cache module")
        register_count = 0
        for bit, cells in groups.items():
            first = cells[0]
            outputs = set()
            for cell in cells:
                if limit is not None and cell["native_max_fanout"] != limit:
                    raise ValueError("Missing or different native fanout attribute")
                if (cell["parameters"] != first["parameters"] or
                        any(cell["ports"][port] != first["ports"][port]
                            for port in ("C", "CE", "CLK", "D"))):
                    raise ValueError("Address copies disagree on input, enable, clock, or reset")
                if cell["ports"]["Q"] in outputs:
                    raise ValueError("Address copies drive the same output net")
                outputs.add(cell["ports"]["Q"])
            register_count += len(cells)
        reports[name] = {
            "register_prefix": register_prefix,
            "address_register_cells": register_count,
            "address_bits": len(groups),
            "extra_same_bit_cells": register_count - len(groups),
            "maximum_direct_sink_pin_occurrences": max(
                cell["direct_sink_pin_occurrences"] for cells in groups.values() for cell in cells),
            "bits": {str(bit): cells for bit, cells in sorted(groups.items())},
        }
    if not reports:
        raise ValueError("No supported native cache modules")
    if limit is not None and not any(report["extra_same_bit_cells"] for report in reports.values()):
        raise ValueError("No replicated address register evidence")
    return reports


def main():
    parser = argparse.ArgumentParser(description="Audit ADS cache address register copies; not formal equivalence or routed fanout")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--register-prefix", default="request_address")
    parser.add_argument("--inspect-only", action="store_true",
                        help="Report connections without requiring cell-level attributes; not a constraint validation")
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.limit <= 0:
            raise ValueError("Fanout limit must be positive")
        baseline = inspect_netlist(args.baseline.read_text(encoding="utf-8-sig"),
                                   register_prefix=args.register_prefix)
        candidate = inspect_netlist(args.candidate.read_text(encoding="utf-8-sig"),
                                    None if args.inspect_only else args.limit, args.register_prefix)
        if set(baseline) != set(candidate):
            raise ValueError("Cache module inventory differs")
        report = {
            "measurement_kind": "native_synthesis_direct_pin_audit_not_routed_timing",
            "limit": args.limit, "baseline": baseline, "candidate": candidate,
            "cell_attribute_validation": "not_checked" if args.inspect_only else "all_address_cells_match",
            "netlist_sha256": {str(path): sha256(path.read_bytes()).hexdigest().upper()
                               for path in (args.baseline, args.candidate)},
        }
        with args.json.open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
            output.write("\n")
        for name in candidate:
            print(name, "registers", baseline[name]["address_register_cells"],
                  "->", candidate[name]["address_register_cells"], "max direct sink pin occurrences",
                  baseline[name]["maximum_direct_sink_pin_occurrences"],
                  "->", candidate[name]["maximum_direct_sink_pin_occurrences"])
    except (OSError, ValueError) as error:
        parser.exit(1, f"Invalid native fanout evidence: {error}\n")


if __name__ == "__main__":
    main()
