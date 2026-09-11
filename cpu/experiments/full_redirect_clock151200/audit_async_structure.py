import argparse
import hashlib
import json
import re
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
DEFAULT_NETLIST = EXPERIMENT / "build/ila/20260910-redirect-clock151200-seed1/netlist.v"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit_text(text):
    chains = [("rv32_uart", "rx_meta", "rx_sync", "serial_rx", "GTP_DFF_P", "P"),
              ("rv32_peripherals", "gpio_meta[0]", "gpio_sync[0]", "gpio_input[0]", "GTP_DFF_C", "C"),
              ("rv32_peripherals", "gpio_meta[1]", "gpio_sync[1]", "serial_rx", "GTP_DFF_C", "C"),
              ("rv32_board_top", "reset_pipe[0]", "reset_pipe[1]", "1'b1", "GTP_DFF_C", "C")]
    result = []
    for module_name, first, second, source, primitive, reset_port in chains:
        modules = re.findall(r"\bmodule\s+" + module_name + r"\b(.*?)\bendmodule", text, re.S)
        require(len(modules) == 1, "Missing or ambiguous module: " + module_name)
        module = modules[0]
        cells = []
        pattern = r"\b(GTP_DFF_\w+)\s*/\*.*?\*/\s*#\(.*?\)\s+[^\s(]+\s*\((.*?)\);"
        for kind, body in re.findall(pattern, module, re.S):
            ports = re.findall(r"\.(\w+)\s*\(([^()]*)\)", body)
            require(len(dict(ports)) == len(ports), "Duplicate cell port")
            cells.append((kind, {name: value.strip() for name, value in ports}))
        selected = []
        for target in (first, second):
            matches = [(kind, ports) for kind, ports in cells if ports.get("Q") == target]
            require(len(matches) == 1, "Missing or ambiguous synchronizer: " + target)
            kind, ports = matches[0]
            require(kind == primitive and ports.get("CLK") == "clk", "Wrong synchronizer kind or clock")
            selected.append(ports)
        require(selected[0].get("D") == source, "Wrong first-stage input")
        require(selected[1].get("D") == first, "Synchronizer bypass or intermediate logic")
        require(selected[0].get(reset_port) and selected[0].get(reset_port) == selected[1].get(reset_port),
                "Synchronizer reset mismatch")
        uses = re.findall(r"\.(\w+)\s*\(\s*" + re.escape(first) + r"\s*\)", module)
        require(sorted(uses) == ["D", "Q"], "First-stage signal has additional named-port fanout")
        require(not re.search(r"\bassign\b[^;]*" + re.escape(first) + r"[^;]*;", module),
                "First-stage signal has assign fanout")
        result.append({"module": module_name, "first": first, "second": second,
                       "source": source, "primitive": primitive, "reset": selected[0][reset_port]})
    return {"scope": "bounded synthesized-cell connectivity check, not CDC or electrical signoff",
            "chains": result, "structural_checks_passed": True,
            "post_route_placement_checked": False, "metastability_mtbf_proven": False,
            "reset_recovery_removal_proven": False, "electrical_qualified": False}


def audit(filename):
    result = audit_text(filename.read_text(encoding="utf-8-sig"))
    result["netlist"] = str(filename)
    result["netlist_sha256"] = hashlib.sha256(filename.read_bytes()).hexdigest().upper()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = audit(arguments.netlist)
    arguments.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))

