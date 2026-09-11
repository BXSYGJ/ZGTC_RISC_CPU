import json
import re
from collections import Counter

from audit_binding import ROOT, digest, require
from audit_async_structure import audit_text as audit_chains

STAGES = ("20260910-redirect-clock151200-seed1", "20260911-redirect-clock151200-v1-seed1", "20260911-redirect-clock151200-scope-seed1")
PORT = re.compile(r"\.([A-Za-z_]\w*|\\\S+)\s*\(([^()]*)\)")
PAD = "{1'bx,1'bx,1'bx,1'bx,1'bx,1'bx,1'bx,"
CONSUMERS = {
    "rv32_uart": {"serial_rx": [("D", "serial_rx")]},
    "rv32_peripherals": {"serial_rx": [("D", "serial_rx"), ("serial_rx", "serial_rx")], "gpio_input": [("D", "gpio_input[0]")]},
    "rv32_soc": {"serial_rx": [("serial_rx", "serial_rx")], "gpio_input": [("gpio_input", PAD + "gpio_input[0]}")]},
    "rv32_board_top": {"uart_rx": [("serial_rx", "uart_rx")], "key": [("I0", "key")], "N7": [("Z", "N7"), ("gpio_input", PAD + "N7}")]},
    "pds_soc_top": {"uart_rx": [("I", "uart_rx")], "nt_uart_rx": [("O", "nt_uart_rx"), ("uart_rx", "nt_uart_rx")],
                    "key": [("I", "key")], "nt_key": [("O", "nt_key"), ("key", "nt_key")]},
}
LINKS = (
    ("pds_soc_top", "GTP_INBUF", "uart_rx_ibuf", {"I": "uart_rx", "O": "nt_uart_rx"}),
    ("pds_soc_top", "GTP_INBUF", "key_ibuf", {"I": "key", "O": "nt_key"}),
    ("pds_soc_top", "rv32_board_top", "board", {"uart_rx": "nt_uart_rx", "key": "nt_key"}),
    ("rv32_board_top", "GTP_LUT1", "N7_vname", {"I0": "key", "Z": "N7"}),
    ("rv32_board_top", "rv32_soc", "soc", {"serial_rx": "uart_rx", "gpio_input": PAD + "N7}"}),
    ("rv32_soc", "rv32_peripherals", "peripherals", {"serial_rx": "serial_rx", "gpio_input": PAD + "gpio_input[0]}"}),
    ("rv32_peripherals", "rv32_uart", "uart", {"serial_rx": "serial_rx"}),
)


def normalized(value):
    return re.sub(r"\s+", "", value)


def module_body(text, name):
    matches = re.findall(r"\bmodule\s+" + re.escape(name) + r"\b(.*?)\bendmodule", text, re.S)
    require(len(matches) == 1, "Missing or ambiguous input-path module: " + name)
    body = re.sub(r"/\*.*?\*/|\(\*.*?\*\)|//[^\n]*", " ", matches[0], flags=re.S)
    require(");" in body, "Missing module port header")
    return body.split(");", 1)[1]


def contains(expression, signal):
    return re.search(r"(?<![\w$])" + re.escape(signal) + r"(?![\w$])", expression) is not None


def audit_text(text):
    chains = audit_chains(text)
    modules = {name: module_body(text, name) for name in CONSUMERS}
    results = []
    for name, signals in CONSUMERS.items():
        body = modules[name]
        connections = [(port, normalized(expression)) for port, expression in PORT.findall(body)]
        leftover = PORT.sub(" ", body)
        leftover = re.sub(r"\bwire\s+(?:\[\d+:\d+\]\s*)?(?:[A-Za-z_][\w$]*\s*,\s*)*[A-Za-z_][\w$]*\s*;", " ", leftover)
        for signal, expected in signals.items():
            actual = [(port, expression) for port, expression in connections if contains(expression, signal)]
            require(Counter(actual) == Counter(expected), "Unexpected raw-input consumer: " + name + "." + signal)
            require(not contains(leftover, signal), "Unparsed raw-input use or assignment: " + name + "." + signal)
            results.append({"module": name, "signal": signal, "connections": actual})
    for parent, kind, instance, expected in LINKS:
        pattern = r"\b" + re.escape(kind) + r"\s*(?:#\([^;]*?\)\s*)?" + re.escape(instance) + r"\s*\((.*?)\);"
        matches = re.findall(pattern, modules[parent], re.S)
        require(len(matches) == 1, "Missing or ambiguous input-path instance: " + parent + "." + instance)
        ports = [(port, normalized(expression)) for port, expression in PORT.findall(matches[0])]
        require(len(dict(ports)) == len(ports), "Duplicate hierarchy port")
        for port, value in expected.items():
            require(dict(ports).get(port) == value, "Raw-input hierarchy mismatch: " + parent + "." + instance + "." + port)
    return {"scope": "bounded UART/KEY raw-input fanout and hierarchy audit of synthesized input netlist; not complete CDC or electrical signoff",
            "raw_input_paths_passed": True, "consumers": results, "hierarchy_links_checked": len(LINKS),
            "synchronizer_chains": chains["chains"], "reset_path_coverage": "existing two-register structural check only",
            "post_route_placement_checked": False, "electrical_qualified": False, "hardware_validated": False}


def audit():
    reports = []
    for name in STAGES:
        stage = ROOT / "build/ila" / name
        invocation = json.loads((stage / "invocation.json").read_text(encoding="utf-8-sig"))
        netlist = stage / "netlist.v"
        require(digest(netlist) == invocation["Inputs"]["netlist.v"], "Implementation input netlist changed")
        result = audit_text(netlist.read_text(encoding="utf-8-sig"))
        result.update(stage=name, netlist_sha256=digest(netlist), implementation_invocation_sha256=digest(stage / "invocation.json"))
        reports.append(result)
    receipt = {"schema": 1, "reports": reports, "auditor_sha256": digest(ROOT / "audit_async_entries.py")}
    output = ROOT / "build/async-input-paths.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not output.exists() or output.read_text(encoding="utf-8") == text, "Refusing to overwrite changed input-path audit")
    output.write_text(text, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
