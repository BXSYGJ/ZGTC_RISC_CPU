"""Reconstruct actual mapped CPU ROM reads before allowing place and route.

The reconstruction follows the installed Pango DRM simulation models: INIT
parameters contain consecutive nine-bit cells, while the data pins omit or
retain parity according to DATA_WIDTH. Actual address, chip-select and output
connections are evaluated in the synthesized module, including LUTs between
the ROMs and their consumers. Inactive ROM outputs are tested as both zero and
all ones, so an omitted output selector cannot pass by assuming a zero value.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys

SCHEMA = "rtos-mapped-rom-v1"
ARRAYS = {"imem_even": "i_even_q", "imem_odd": "i_odd_q", "rom_d": "d_rom_q"}
HERE = Path(__file__).resolve().parent
MODEL_NAMES = ["GTP_DRM18K_E1.v", "GTP_DRM36K_E1.v", "GTP_LUT6CARRY.v", "GTP_LUT6D.v",
               "GTP_INV.v", "GTP_MUX2LUT7.v", "GTP_MUX2LUT8.v"] + ["GTP_LUT" + str(n) + ".v" for n in range(1, 7)]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record(path: Path, role: str) -> dict:
    data = path.read_bytes()
    return {"role": role, "path": path.resolve().as_posix(), "bytes": len(data), "sha256": digest(data)}


def canonical(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\\", ""))


def literal(value: str) -> tuple[int, int]:
    value = value.strip().replace("_", "")
    if value.startswith('"'):
        raise ValueError("String is not a bit vector: " + value)
    match = re.fullmatch(r"(?:(\d+))?'([bBoOdDhH])([0-9a-fA-F]+)", value)
    if match:
        width = int(match[1] or "32")
        return int(match[3], {"b": 2, "o": 8, "d": 10, "h": 16}[match[2].lower()]), width
    if re.fullmatch(r"\d+", value):
        return int(value), 32
    raise ValueError("Expected a known Verilog constant: " + value)


def fields(text: str) -> dict[str, str]:
    return {canonical(match[1]): match[2].strip()
            for match in re.finditer(r"\.(\\[^\s(]+|\w+)\s*\(([^()]*)\)", text)}


def bits(expression: str, widths: dict[str, int]) -> list[str]:
    """Expand a constant, bit, vector or flat concatenation, least bit first."""
    value = expression.strip()
    if not value:
        return []
    if value.startswith("{"):
        result = []
        for part in reversed(value[1:-1].split(",")):
            result.extend(bits(part, widths))
        return result
    try:
        number, width = literal(value)
        return ["1'b" + str((number >> n) & 1) for n in range(width)]
    except ValueError:
        pass
    name = canonical(value)
    if "[" in name or widths.get(name, 1) == 1:
        return [name]
    return [name + "[" + str(n) + "]" for n in range(widths[name])]


_FUNCTION_CACHE = {}


def driver_function(driver: tuple) -> tuple[list[str], int]:
    """Reduce a primitive's truth table after constant pins and tied inputs.

    Unused LUT pins must disappear before traversing the graph. PDS connects
    some otherwise unused LUT pins back into another cone; traversing those
    pins would invent a combinational dependency absent from the actual INIT.
    """
    kind, pin, params, ports = driver
    key = (kind, pin, tuple(sorted(params.items())), tuple(sorted(ports.items())))
    if key in _FUNCTION_CACHE:
        return _FUNCTION_CACHE[key]
    if kind == "GTP_INV":
        port_names = ["I"]
    elif kind.startswith("GTP_MUX"):
        port_names = ["I0", "I1", "S"]
    else:
        count = 5 if pin == "Z5" else 6 if "CARRY" in kind else int(re.search(r"LUT(\d)", kind)[1])
        port_names = ["I" + str(n) for n in range(count)] + (["CIN"] if "CARRY" in kind else [])
    names = [canonical(ports.get(name) or "1'b0") for name in port_names]
    variables = list(dict.fromkeys(name for name in names if name not in ("1'b0", "1'b1")))
    truth = 0
    for row in range(1 << len(variables)):
        values = {name: (row >> n) & 1 for n, name in enumerate(variables)} | {"1'b0": 0, "1'b1": 1}
        pins = {port: values[name] for port, name in zip(port_names, names)}
        if kind == "GTP_INV":
            value = 1 - pins["I"]
        elif kind.startswith("GTP_MUX"):
            value = pins["I" + str(pins["S"])]
        elif kind == "GTP_LUT6CARRY":
            index = sum(pins["I" + str(n)] << n for n in range(5))
            init = literal(params["INIT"])[0]
            low, high = (init >> index) & 1, (init >> (index + 32)) & 1
            if pin == "COUT":
                carry = pins["I5"] if params.get("I5_TO_CARRY", '"TRUE"') == '"TRUE"' else high
                value = pins["CIN"] if low else carry
            else:
                select = pins["I5"] if params.get("I5_TO_LUT", '"FALSE"') == '"TRUE"' else pins["CIN"]
                value = high if select else low
        else:
            index = sum(pins["I" + str(n)] << n for n in range(count))
            value = (literal(params["INIT"])[0] >> index) & 1
        truth |= value << row
    support = [n for n in range(len(variables)) if any(((truth >> row) ^ (truth >> (row ^ (1 << n)))) & 1
                                                    for row in range(1 << len(variables)))]
    reduced = 0
    for row in range(1 << len(support)):
        original = sum(((row >> bit) & 1) << position for bit, position in enumerate(support))
        reduced |= ((truth >> original) & 1) << row
    result = [variables[n] for n in support], reduced
    _FUNCTION_CACHE[key] = result
    return result


class Module:
    def __init__(self, name: str, text: str):
        self.name, self.text = name, text
        self.widths = {}
        self.directions = {}
        self.drivers = {}
        self.roms = []
        for declaration in re.finditer(r"\b(wire|input|output)\s*(?:\[(\d+):0\])?\s+(\\[^\n,;()]+|\w+)", text):
            width = int(declaration[2] or "0") + 1
            net = canonical(declaration[3])
            self.widths[net] = width
            if declaration[1] != "wire":
                self.directions[net] = declaration[1]
        pattern = r"\b(GTP_\w+)\s*(?:/\*(.*?)\*/\s*)?(?:#\((.*?)\)\s*)?(\\[^\s]+|\w+)\s*\((.*?)\);"
        for match in re.finditer(pattern, text, re.S):
            kind, source, parameters, name, ports = match.groups()
            params, ports = fields(parameters or ""), fields(ports)
            item = {"primitive": kind, "source": (source or "").strip(), "name": canonical(name),
                    "parameters": params, "ports": ports, "literal": match[0]}
            if kind in ("GTP_DRM18K_E1", "GTP_DRM36K_E1"):
                self.roms.append(item)
            elif kind.startswith("GTP_LUT") and "INIT" in params:
                for pin in ("Z", "Z5", "COUT"):
                    if ports.get(pin):
                        self.drivers[canonical(ports[pin])] = (kind, pin, params, ports)
            elif kind in ("GTP_MUX2LUT7", "GTP_MUX2LUT8", "GTP_INV"):
                for pin in ("Z", "O"):
                    if ports.get(pin):
                        self.drivers[canonical(ports[pin])] = (kind, pin, params, ports)
        for assignment in re.finditer(r"\bassign\s+([^=;]+)=\s*([^;]+);", text):
            left, right = bits(assignment[1], self.widths), bits(assignment[2], self.widths)
            if len(left) == len(right):
                for a, b in zip(left, right):
                    self.drivers[a] = ("alias", b)

    def evaluate(self, expression: str, context: dict[str, int], cache: dict[str, int]) -> int:
        def one(net: str, seen: set[str]) -> int:
            if net in context:
                return context[net]
            if net in cache:
                return cache[net]
            if net.startswith("1'b"):
                return int(net[-1])
            if net in seen or net not in self.drivers:
                raise ValueError("Unresolved mapped address/output net in " + self.name + ": " + net)
            seen = seen | {net}
            driver = self.drivers[net]
            if driver[0] == "alias":
                value = one(driver[1], seen)
            else:
                inputs, truth = driver_function(driver)
                index = sum(one(name, seen) << n for n, name in enumerate(inputs))
                value = (truth >> index) & 1
            cache[net] = value
            return value
        return sum(one(net, set()) << n for n, net in enumerate(bits(expression, self.widths)))


def module_list(text: str) -> list[Module]:
    return [Module(match[1], match[0]) for match in re.finditer(r"^module\s+(\w+)\b.*?^endmodule", text, re.M | re.S)]


def connect_hierarchy(root: Module, modules: list[Module]) -> None:
    """Bring the actual child-module LUT drivers into the ROM module graph."""
    definitions = {module.name: module for module in modules}
    combined = {}

    def qualify(net: str, prefix: str) -> str:
        return net if net.startswith("1'b") else prefix + net

    def visit(module: Module, prefix: str) -> None:
        for net, driver in module.drivers.items():
            if driver[0] == "alias":
                combined[prefix + net] = ("alias", qualify(driver[1], prefix))
            else:
                kind, pin, params, ports = driver
                rewritten = {key: qualify(canonical(value), prefix) if value else "1'b0"
                             for key, value in ports.items()}
                combined[prefix + net] = (kind, pin, params, rewritten)
        names = "|".join(re.escape(name) for name in definitions)
        pattern = r"\b(" + names + r")\s+(\\[^\s]+|\w+)\s*\((.*?)\);"
        for match in re.finditer(pattern, module.text, re.S):
            child = definitions[match[1]]
            child_prefix = prefix + canonical(match[2]) + "/"
            visit(child, child_prefix)
            for port, expression in fields(match[3]).items():
                port = canonical(port)
                if port not in child.directions:
                    continue
                local = bits(port, child.widths)
                parent = bits(expression, module.widths)
                if len(local) != len(parent):
                    raise ValueError("Mapped hierarchy port width mismatch: " + child_prefix + port)
                for a, b in zip(local, parent):
                    a, b = child_prefix + a, qualify(b, prefix)
                    if a == b:
                        continue
                    if child.directions[port] == "input":
                        combined[a] = ("alias", b)
                    elif not b.startswith("1'b"):
                        combined[b] = ("alias", a)
    visit(root, "")
    root.drivers = combined


def prove_address_contract(module: Module) -> dict:
    """Prove actual cross-hierarchy bank selectors with a Boolean SMT solver."""
    import z3
    leaves = {}

    def lookup(cuts: set[str]):
        cache = {}
        pending = set()

        def lut(init: int, count: int, inputs: list):
            values = [z3.BoolVal(bool((init >> n) & 1)) for n in range(1 << count)]
            for select in inputs:
                values = [a if z3.eq(a, b) else z3.If(select, b, a)
                          for a, b in zip(values[0::2], values[1::2])]
            return z3.simplify(values[0])

        def expression(net: str):
            if net.startswith("1'b") and net[-1] in "01":
                return z3.BoolVal(net[-1] == "1")
            if net in cache:
                return cache[net]
            if net in cuts or net not in module.drivers:
                value = leaves.setdefault(net, z3.Bool(net))
            else:
                if net in pending:
                    raise ValueError("Combinational loop in actual mapped ROM selector: " + net)
                pending.add(net)
                driver = module.drivers[net]
                if driver[0] == "alias":
                    value = expression(driver[1])
                else:
                    names, truth = driver_function(driver)
                    value = lut(truth, len(names), [expression(name) for name in names])
                pending.remove(net)
                value = z3.simplify(value)
            cache[net] = value
            return value
        return expression

    checks = []
    expression = lookup(set())
    request_references = [name[:-len("i_req_address[2]")] for name, driver in module.drivers.items()
                          if name.endswith("/i_req_address[2]") and driver[0] != "alias"]
    if len(request_references) != 1:
        raise ValueError("Expected one actual frontend request bus driver")
    reference = request_references[0]
    for bit in range(11):
        first, second = reference + "i_req_address[" + str(bit + 3) + "]", reference + "i_req_pair_address[" + str(bit + 3) + "]"
        select = expression(reference + "i_req_address[2]")
        for array in ("imem_even", "imem_odd"):
            target = ("i_even_index" if array == "imem_even" else "i_odd_index") + "[" + str(bit) + "]"
            expected = z3.If(select, expression(second), expression(first)) if array == "imem_even" else z3.If(select, expression(first), expression(second))
            solver = z3.Solver()
            solver.set(timeout=30000)
            solver.add(z3.Xor(expression(target), expected))
            result = solver.check()
            if result != z3.unsat:
                raise ValueError("Mapped bank address equivalence failed: " + target + " result=" + str(result) +
                                 (" model=" + str(solver.model()) if result == z3.sat else ""))
            checks.append({"array": array, "index_bit": bit, "equivalent": True, "solver_result": "unsat"})
    return {"method": "SMT equivalence of actual cross-hierarchy LUT/carry/port-alias graph; CPU state is unconstrained",
            "solver": "z3-solver", "solver_version": z3.get_version_string(),
            "request_bus_reference": reference,
            "all_bank_index_bits_equivalent": True, "checks": checks,
            "compositional_reconstruction": "Physical DRM ports are scanned by their logical array indices only after all 22 mapped request-to-bank index equations have been proven equivalent"}


def init_cells(item: dict) -> list[int]:
    count = 128 if "36K" in item["primitive"] else 64
    cells = []
    for number in range(count):
        key = "INIT_" + format(number, "02X")
        if key not in item["parameters"]:
            raise ValueError("Missing actual mapped " + key + " in " + item["name"])
        value, width = literal(item["parameters"][key])
        if width != 288:
            raise ValueError("Unexpected INIT width")
        cells.extend((value >> (9 * n)) & 511 for n in range(32))
    return cells


def raw_read(cells: list[int], address: int, width: int, is_18k: bool) -> int:
    address &= (1 << (14 if is_18k else 15)) - 1
    if width in (1, 2, 4):
        offset = ((address & 7) // width) * width
        return (cells[address >> 3] >> offset) & ((1 << width) - 1)
    count = 1 if width <= 9 else 2 if width <= 18 else 4
    row = address >> (3 if count == 1 else 4 if count == 2 else 5)
    stride = 9 if width in (9, 18, 36) else 8
    return sum((cells[row * count + n] & ((1 << stride) - 1)) << (stride * n) for n in range(count))


def physical_output(raw: int, width: int, pin: int, is_18k: bool, port: str) -> int:
    if is_18k and width >= 32:
        # The 18K single-port wide mode combines both 18-bit output buses.
        if pin % 9 == 8 and width == 32:
            return 0
        bit = pin if width == 36 else pin - pin // 9
        bit += (18 if width == 36 else 16) if port == "B" else 0
    elif width in (1, 2, 4, 8):
        bit = (pin % 9) % width
    elif width == 9:
        bit = pin % 9
    elif width in (16, 32):
        if pin % 9 == 8:
            return 0
        bit = pin - pin // 9
    else:
        bit = pin
    return (raw >> bit) & 1


def word_bytes(words: list[int]) -> bytes:
    return b"".join(word.to_bytes(4, "little") for word in words)


def required_inputs(run: Path, netlist: Path) -> list[tuple[Path, str]]:
    models = Path(os.environ.get("PDS_ROOT", "D:/PDS_2022.2-SP6.4")) / "arch/vendor/pango/verilog/simulation"
    spec = importlib.util.find_spec("z3")
    if not spec or not spec.origin:
        raise RuntimeError("Install the mapped ROM proof dependency: python -m pip install --user z3-solver==5.4.1.0")
    solver = Path(spec.origin).parent
    inputs = [(netlist, "synthesized_netlist"), (run / "device_map/instrec_top_map.adf", "mapped_database"),
              (run / "INPUTS.json", "frozen_input_manifest"), (run / "RESULT.json", "mapped_flow_result"),
              (Path(__file__), "auditor_source")]
    inputs += [(models / name, "vendor_primitive_model") for name in MODEL_NAMES]
    inputs += [(path, "solver_runtime") for path in sorted(solver.rglob("*")) if path.suffix in (".py", ".dll")]
    for suffix in ("", "_even", "_odd"):
        relative = "src/cpu/prog_pacerv" + suffix + ".hex"
        inputs.extend(((run / "inputs" / relative, "frozen_firmware" + suffix),
                       (run / relative, "synthesizer_firmware" + suffix)))
    return inputs


def context_for(index: int, array: str, module: Module, contract: dict) -> dict[str, int]:
    if not contract.get("all_bank_index_bits_equivalent") or len(contract.get("checks", [])) != 22:
        raise ValueError("Physical ROM reconstruction requires the independent mapped-address proof")
    context = {}
    address = index * (4 if array == "rom_d" else 8)
    vectors = {"i_req_address": address, "i_req_pair_address": address + 4,
               "dd_req_address": address, "d_req_address": address,
               "i_even_index": index, "i_odd_index": index}
    for name in module.widths:
        base = name.rsplit("/", 1)[-1]
        if base in vectors:
            for bit in range(module.widths[name]):
                context[name + "[" + str(bit) + "]"] = (vectors[base] >> bit) & 1
    for name, value in vectors.items():
        for bit in range(32):
            context[name + "[" + str(bit) + "]"] = (value >> bit) & 1
    for name in ("i_req_valid", "i_req_ready", "i_rsp_ready", "d_req_valid", "d_req_ready", "d_rsp_ready", "rst_n", "maintenance_ready"):
        context[name] = 1
    for name in ("i_pend", "d_pend", "d_req_write", "dd_active", "d_err_q"):
        context[name] = 0
    return context


def reconstruct(module: Module, array: str, expected: list[int], contract: dict) -> tuple[dict, list[int]]:
    selected = [item for item in module.roms if array in item["source"] or array in item["name"]]
    if not selected:
        raise ValueError("No mapped DRM instances for actual array " + array)
    for item in selected:
        item["cells"] = init_cells(item)
    actual = []
    for index in range(len(expected)):
        observed = []
        for poison in (0, 1):
            context = context_for(index, array, module, contract)
            for item in selected:
                ports, params = item["ports"], item["parameters"]
                cache = {}
                is_18k = "18K" in item["primitive"]
                wide_18 = is_18k and literal(params["DATA_WIDTH_A"])[0] >= 32
                for port in ("A", "B"):
                    output = bits(ports.get("DO" + port, ""), module.widths)
                    if not output:
                        continue
                    read_port = "A" if wide_18 else port
                    width = literal(params["DATA_WIDTH_" + read_port])[0]
                    if module.evaluate(ports.get("WE" + read_port, "1'b0"), context, cache) != 0:
                        raise ValueError("Mapped ROM has an active write enable")
                    if module.evaluate(ports.get("CE" + read_port, "1'b0"), context, cache) != 1:
                        raise ValueError("Mapped ROM read clock enable is inactive for an accepted request")
                    if module.evaluate(ports.get("ADDR" + read_port + "_HOLD", "1'b0"), context, cache) != 0:
                        raise ValueError("Mapped ROM address hold is active")
                    if module.evaluate(ports.get("RST" + read_port, "1'b0"), context, cache) != 0:
                        raise ValueError("Mapped ROM reset is active")
                    if canonical(ports.get("CLK" + read_port, "")) != "clk":
                        raise ValueError("Mapped ROM read port is not connected to the CPU clock")
                    if literal(params.get("DO" + read_port + "_REG", "0"))[0] != 0:
                        raise ValueError("Unexpected registered DRM output latency")
                    address = module.evaluate(ports["ADDR" + read_port], context, cache)
                    selected_cs = module.evaluate(ports.get("CS" + read_port, "3'b000"), context, cache)
                    cs_mask = literal(params.get("CS" + read_port + "_MASK", "3'b000"))[0]
                    enabled = selected_cs == cs_mask
                    raw = raw_read(item["cells"], address, width, is_18k)
                    for pin, net in enumerate(output):
                        context[net] = physical_output(raw, width, pin, is_18k, port) if enabled else poison
            output = sum(module.evaluate(ARRAYS[array] + "[" + str(bit) + "]", context, {}) << bit for bit in range(32))
            observed.append(output)
        if observed[0] != observed[1]:
            raise ValueError(f"Inactive ROM output affects {array}[{index}]: {observed}")
        actual.append(observed[0])
    differences = [{"word": n, "expected": f"{e:08x}", "actual": f"{a:08x}"}
                   for n, (e, a) in enumerate(zip(expected, actual)) if e != a]
    evidence = []
    for item in selected:
        params = item["parameters"]
        evidence.append({"module": module.name, "name": item["name"], "source": item["source"],
                         "primitive": item["primitive"], "init_cell_count": len(item["cells"]),
                         "init_cells_sha256": digest(b"".join(cell.to_bytes(2, "little") for cell in item["cells"])),
                         "parameters": {key: value for key, value in params.items() if not re.fullmatch(r"INIT_[0-9A-F]{2}", key)},
                         "ports": item["ports"], "literal_sha256": digest(item["literal"].encode("utf-8"))})
    report = {"array": array, "expected_words": len(expected), "reconstructed_words": len(actual),
              "expected_words_sha256": digest(word_bytes(expected)), "reconstructed_words_sha256": digest(word_bytes(actual)),
              "all_words_match": not differences, "zero_tail_verified": not differences,
              "address_and_output_connections_evaluated": True, "inactive_output_poison_values": [0, 1],
              "accepted_request_read_controls_verified": True,
              "mismatches": differences[:16], "instances": evidence}
    return report, actual


def verify_report(run: Path) -> dict:
    run = run.resolve(strict=True)
    report = json.loads((run / "ROM_AUDIT.json").read_text(encoding="utf-8"))
    if (report.get("schema") != SCHEMA or report.get("status") != "pass" or report.get("errors") or
            report.get("exit_status") != 0 or Path(report.get("pds_run", "")).resolve() != run):
        raise RuntimeError("A passing ROM audit for this exact mapped run is required")
    candidates = list((run / "synthesize").glob("*_syn.vm"))
    if len(candidates) != 1:
        raise RuntimeError("Expected exactly one actual synthesized netlist")
    required = {(path.resolve().as_posix(), role) for path, role in required_inputs(run, candidates[0])}
    recorded = {(Path(item["path"]).resolve().as_posix(), item["role"]) for item in report["inputs"]}
    if recorded != required or len(report["inputs"]) != len(required):
        raise RuntimeError("ROM audit input roles or exact file coverage is incomplete")
    for item in report["inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path.read_bytes()) != item["sha256"]:
            raise RuntimeError("Mapped ROM audit input changed: " + str(path))
    if report["netlist"] != record(candidates[0], "synthesized_netlist"):
        raise RuntimeError("ROM audit netlist record is inconsistent")
    manifest = json.loads((run / "INPUTS.json").read_text(encoding="utf-8"))
    depth = manifest["rom_bytes"] // 4
    words = [int(word, 16) for word in (run / "inputs/src/cpu/prog_pacerv.hex").read_text(encoding="ascii").split()]
    expected = {"rom_d": words + [0] * (depth - len(words)),
                "imem_even": words[0::2] + [0] * (depth // 2 - len(words[0::2])),
                "imem_odd": words[1::2] + [0] * (depth // 2 - len(words[1::2]))}
    if len(report["memories"]) != 3 or {m["array"] for m in report["memories"]} != set(ARRAYS):
        raise RuntimeError("The ROM audit does not cover all three actual arrays")
    for memory in report["memories"]:
        if (not memory["all_words_match"] or not memory["zero_tail_verified"] or
                not memory["address_and_output_connections_evaluated"] or
                not memory["accepted_request_read_controls_verified"] or memory.get("mismatches") or
                memory["expected_words"] != len(expected[memory["array"]]) or
                memory["reconstructed_words"] != len(expected[memory["array"]]) or
                memory["expected_words_sha256"] != digest(word_bytes(expected[memory["array"]])) or
                memory["expected_words_sha256"] != memory["reconstructed_words_sha256"] or not memory["instances"]):
            raise RuntimeError("Mapped ROM contents or address contract failed")
    contract = report["address_contract"]
    checks = {(item["array"], item["index_bit"]) for item in contract["checks"]
              if item.get("equivalent") and item.get("solver_result") == "unsat"}
    if not contract["all_bank_index_bits_equivalent"] or checks != {(array, bit) for array in ("imem_even", "imem_odd") for bit in range(11)}:
        raise RuntimeError("Mapped request-to-ROM address proof is incomplete")
    reconstruction = report["reconstruction"]
    if (reconstruction["firmware_bytes"] != len(words) * 4 or reconstruction["firmware_words"] != len(words) or
            reconstruction["firmware_sha256"] != digest(word_bytes(words)) or
            reconstruction["reset_instruction"] != f"{words[0]:08x}" or
            reconstruction["firmware_sha256"] != reconstruction["from_instruction_banks_sha256"] or
            reconstruction["firmware_sha256"] != reconstruction["from_data_rom_sha256"]):
        raise RuntimeError("Reconstructed firmware differs from the input image")
    if report["literal_result"] != f"MAPPED_ROM_PASS firmware_bytes={len(words)*4} arrays=3":
        raise RuntimeError("ROM audit literal result is inconsistent")
    return report


def audit(run: Path) -> dict:
    run = run.resolve(strict=True)
    manifest_path = run / "INPUTS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = list((run / "synthesize").glob("*_syn.vm"))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one actual synthesized netlist")
    netlist = candidates[0]
    inputs = [record(path, role) for path, role in required_inputs(run, netlist)]
    images = []
    for suffix in ("", "_even", "_odd"):
        relative = "src/cpu/prog_pacerv" + suffix + ".hex"
        frozen = run / "inputs" / relative
        used = run / relative
        if frozen.read_bytes() != used.read_bytes():
            raise ValueError("Synthesizer ROM file differs from frozen input: " + relative)
        images.append([int(word, 16) for word in frozen.read_text(encoding="ascii").split()])
    words, even, odd = images
    if even != words[0::2] or odd != words[1::2]:
        raise ValueError("The input parity images do not reconstruct the linear firmware")
    depth = manifest["rom_bytes"] // 4
    if depth != 4096:
        raise ValueError("This mapped board profile requires exactly 16 KiB ROM")
    if len(words) > depth:
        raise ValueError("The firmware exceeds the configured mapped ROM")
    expected = {"rom_d": words + [0] * (depth - len(words)),
                "imem_even": even + [0] * (depth // 2 - len(even)),
                "imem_odd": odd + [0] * (depth // 2 - len(odd))}
    modules = module_list(netlist.read_text(encoding="utf-8", errors="strict"))
    report = {"schema": SCHEMA, "status": "fail", "pds_run": run.as_posix(),
              "created_utc": datetime.now(timezone.utc).isoformat(), "netlist": record(netlist, "synthesized_netlist"),
              "inputs": inputs, "memories": [], "address_contract": {}, "reconstruction": {}, "errors": []}
    actual = {}
    try:
        cpu = next(module for module in modules if module.name == "rv32_cpu_subsys")
        connect_hierarchy(cpu, modules)
        report["address_contract"] = prove_address_contract(cpu)
        for array in ARRAYS:
            found = [module for module in modules if any(array in item["source"] or array in item["name"] for item in module.roms)]
            if len(found) != 1:
                raise ValueError("Expected one mapped module containing " + array + "; found " + str(len(found)))
            memory, actual[array] = reconstruct(found[0], array, expected[array], report["address_contract"])
            report["memories"].append(memory)
        reconstructed = list(itertools.chain.from_iterable(zip(actual["imem_even"], actual["imem_odd"])))[:len(words)]
        data = word_bytes(words)
        report["reconstruction"] = {"firmware_bytes": len(data), "firmware_words": len(words),
                                    "firmware_sha256": digest(data), "from_instruction_banks_sha256": digest(word_bytes(reconstructed)),
                                    "from_data_rom_sha256": digest(word_bytes(actual["rom_d"][:len(words)])),
                                    "reset_instruction": f"{actual['imem_even'][0]:08x}"}
        if all(memory["all_words_match"] for memory in report["memories"]):
            report["status"] = "pass"
    except (ValueError, KeyError, IndexError) as error:
        report["errors"].append(str(error))
    report["exit_status"] = 0 if report["status"] == "pass" else 2
    report["literal_result"] = ("MAPPED_ROM_PASS" if report["status"] == "pass" else "MAPPED_ROM_FAIL") + f" firmware_bytes={len(words)*4} arrays={len(report['memories'])}"
    output = run / "ROM_AUDIT.json"
    if output.exists():
        history = run / "rom_audit_attempts"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        shutil.copyfile(output, history / (stamp + "-ROM_AUDIT.json"))
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["status"] == "pass":
        verify_report(run)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pds-run", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.pds_run)
    print(report["literal_result"])
    for error in report["errors"]:
        print(error)
    print(str(args.pds_run.resolve() / "ROM_AUDIT.json"))
    return report["exit_status"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
