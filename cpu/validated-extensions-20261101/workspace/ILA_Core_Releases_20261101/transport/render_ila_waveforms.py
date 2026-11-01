"""Render source-bound local RTL simulation probe windows as PNG and SVG.

All42 CSV data bits are cross-checked against the recorded VCD at every rising
edge. Configured FPGA frequency, simulator timestamps and accelerated UART
metadata retain separate meanings. No remote platform operation is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
from decimal import Decimal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

class CaptureError(ValueError):
    """A recorded local trace fails a required integrity or semantic check."""


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def validate_pipeline(rows, trigger_pc, require_ex_fire=True, channel40_semantic="frontend_fire"):
    if len(rows) != 1024 or any(len(row) != 43 for row in rows):
        raise CaptureError("Expected 1024 rows of 42 recorded probe bits plus capture predicate")
    marked = [index for index, row in enumerate(rows) if row[42]]
    matched = [index for index in marked
               if sum(rows[index][bit] << bit for bit in range(32)) == trigger_pc
               and (not require_ex_fire or rows[index][38])]
    if not matched or any(index not in matched for index in marked):
        raise CaptureError("Recorded capture predicate differs from requested EX_PC/ex_fire")
    for index, row in enumerate(rows):
        for fire, valid in ((37, 33), (38, 34), (41, 35)):
            if row[fire] and not row[valid]:
                raise CaptureError(f"Pipeline fire/valid invariant failed at sample {index}")
        if index == 1023:
            continue
        following = rows[index + 1]
        if row[37] and not following[34]:
            raise CaptureError(f"ID-to-EX valid transfer failed at sample {index}")
        if row[38] and not following[35]:
            raise CaptureError(f"EX-to-MEM valid transfer failed at sample {index}")
        if following[36] and not row[41]:
            raise CaptureError(f"MEM-to-WB valid transfer failed at sample {index}")
    return {"samples": len(rows), "temporal_pairs_checked": len(rows) - 1,
            "trigger_pc": f"0x{trigger_pc:08X}", "trigger_matching_indices": matched,
            "wb_events": sum(row[36] for row in rows),
            "local_retirement_event_rate": sum(row[36] for row in rows) / len(rows),
            "id_held_cycles": sum(row[33] and not row[37] for row in rows),
            "ex_held_cycles": sum(row[34] and not row[38] for row in rows),
            "mem_held_cycles": sum(row[35] and not row[41] for row in rows),
            "mem_flush_cycles": sum(row[39] for row in rows),
            "channel40_semantic": channel40_semantic,
            channel40_semantic + "_events": sum(row[40] for row in rows),
            "pipeline_checks_passed": True,
            "unprobed_conditions": ["reset", "MEM fault", "early frontend redirects"],
            "frontend_fire_to_next_IF_valid_asserted": False,
            "mem_fire_to_next_WB_valid_asserted": False}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def require_hash(path, expected, label):
    if not isinstance(expected, str) or sha256(path).lower() != expected.lower():
        raise CaptureError(label + " SHA256 mismatch")


def read_elf_symbols(path):
    data = Path(path).read_bytes()
    if data[:6] != b"\x7fELF\x01\x01":
        raise CaptureError("Expected the bound little-endian ELF32 firmware")
    offset = struct.unpack_from("<I", data, 32)[0]
    width, count = struct.unpack_from("<HH", data, 46)
    if width != 40 or offset + width * count > len(data):
        raise CaptureError("Invalid bound ELF section layout")
    sections = [struct.unpack_from("<10I", data, offset + index * width) for index in range(count)]
    symbols = []
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != 16 or section[6] >= len(sections):
            raise CaptureError("Invalid bound ELF symbol table")
        table = sections[section[6]]
        strings = data[table[4]:table[4] + table[5]]
        for pos in range(section[4], section[4] + section[5], 16):
            name, address, size, info, _, _ = struct.unpack_from("<IIIBBH", data, pos)
            if info & 15 != 2 or size <= 0:
                continue
            end = strings.find(b"\0", name)
            if end < 0:
                raise CaptureError("Invalid bound ELF symbol name")
            symbols.append({"name": strings[name:end].decode("ascii"), "address": address, "size": size})
    if not symbols:
        raise CaptureError("Bound ELF contains no sized functions")
    return sorted(symbols, key=lambda symbol: (symbol["address"], symbol["size"], symbol["name"]))


def function_at(pc, symbols):
    matches = [symbol for symbol in symbols if symbol["address"] <= pc < symbol["address"] + symbol["size"]]
    return min(matches, key=lambda symbol: symbol["size"])["name"] if matches else f"0x{pc:08X}"


def runs(values, start, stop):
    index = start
    while index < stop:
        end = index + 1
        while end < stop and values[end] == values[index]:
            end += 1
        yield index, end, values[index]
        index = end


def plot_window(receipt, rows, symbols, origin, output, *, start=0, length=1024, stem="full"):
    stop = min(1024, start + length)
    if start < 0 or start >= stop or stop > 1024:
        raise CaptureError("Invalid plot sample window")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"})
    figure, axis = plt.subplots(figsize=(18, 8.6))
    figure.subplots_adjust(left=0.145, right=0.98, top=0.81, bottom=0.18)
    variant = receipt.get("variant") or "CPU"
    prefix = "SYNTHETIC OFFLINE FIXTURE" if origin["kind"] == "SYNTHETIC_OFFLINE_FIXTURE" else "LOCAL RTL SIMULATION"
    trigger_pc = int(receipt["checks"]["trigger_pc"], 0)
    target_name = function_at(trigger_pc, symbols)
    figure.suptitle(f"{variant} | {target_name} | {prefix}", x=0.145, y=0.97, ha="left", fontsize=16, fontweight="bold")
    checks = receipt["checks"]
    figure.text(0.145, 0.92,
                f"Configured FPGA target: {receipt['configured_clock_hz'] / 1e6:g} MHz | "
                f"edges {start}-{stop - 1} of 1024 | capture predicate: EX_PC=0x{trigger_pc:08X}, EX fire=1 | "
                f"WB events {checks['wb_events']}/1024 ({checks['local_retirement_event_rate']:.4f})",
                fontsize=10, color="#354254")
    if origin["kind"] == "LOCAL RTL SIMULATION":
        period_ns = Decimal(origin["vcd_clock"]["rising_edge_period_ps"]) / 1000
        figure.text(0.145, 0.885,
                    f"Recorded simulator edge spacing: {period_ns:g} ns | "
                    f"accelerated UART configuration: CLOCK_HZ={origin['simulation_clock_hz']}, BAUD={origin['uart_baud']} | "
                    "digital tracks: low=0, high=1", fontsize=9, color="#5E6978")
    array = np.array(rows, dtype=np.int8)
    pcs = [sum(row[bit] << bit for bit in range(32)) for row in rows]
    functions = [function_at(pc, symbols) if row[34] else "(EX invalid)" for pc, row in zip(pcs, rows)]
    palette = ["#DCEAF7", "#E7EFDA", "#F7E6CD", "#E8DFF3", "#D9EEEA", "#F6DCE0"]
    unique = list(dict.fromkeys(functions))
    colors = {name: palette[index % len(palette)] for index, name in enumerate(unique)}
    top = 13.0
    for left, right, name in runs(functions, start, stop):
        axis.add_patch(Rectangle((left, top - 0.35), right - left, 0.7,
                                 facecolor=colors[name], edgecolor="white", linewidth=0.6))
        if (right - left) / (stop - start) >= min(0.16, (len(name) * 7 + 12) / 1480):
            axis.text((left + right) / 2, top, name, ha="center", va="center", fontsize=8, clip_on=True)
    pc_y = 11.8
    previous_label_right = -1e9
    for left, right, pc in runs(pcs, start, stop):
        axis.add_patch(Rectangle((left, pc_y - 0.28), right - left, 0.56,
                                 facecolor="#F3F6FA", edgecolor="#ADB8C6", linewidth=0.55))
        width = right - left
        required = (stop - start) * 77 / 1480
        center = (left + right) / 2
        if width >= required or center - previous_label_right >= required:
            axis.text(center, pc_y, f"{pc:08X}", ha="center", va="center", fontsize=7.5,
                      family="DejaVu Sans Mono", color="#25354B", clip_on=True)
            previous_label_right = center + required / 2
    trigger = receipt["alignment"]["first_aligned_trigger_index"]
    if start <= trigger < stop:
        axis.annotate(f"{pcs[trigger]:08X} at trigger", xy=(trigger + 0.5, pc_y + 0.28),
                      xytext=(trigger + (stop - start) * 0.006, pc_y + 0.51),
                      fontsize=8, color="#A12F36", ha="left", va="center",
                      bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2},
                      arrowprops={"arrowstyle": "-", "color": "#A12F36", "linewidth": 0.65})
    channels = [(32, "IF valid"), (33, "ID valid"), (34, "EX valid"), (35, "MEM valid"),
                (36, "WB / retire event"), (37, "ID fire"), (38, "EX fire"), (41, "MEM fire"),
                (39, "MEM flush"), (40, checks["channel40_semantic"]), (42, "Capture predicate")]
    labels, positions = ["EX function", "EX_PC (hex labels)"], [top, pc_y]
    x = np.arange(start, stop + 1)
    for index, (channel, label) in enumerate(channels):
        y = 10.6 - index
        values = array[start:stop, channel]
        coordinates = np.concatenate([values, values[-1:]]) * 0.56 + y - 0.28
        color = "#BB4045" if channel in (39, 42) else "#246E9A" if channel <= 36 else "#2D8066"
        axis.step(x, coordinates, where="post", color=color, linewidth=1.15)
        axis.axhline(y - 0.35, color="#D7DEE7", linewidth=0.55, zorder=0)
        labels.append(label)
        positions.append(y)
    trigger_positions = [index for index, row in enumerate(rows) if row[42]]
    for position in trigger_positions:
        if start <= position < stop:
            axis.axvline(position, color="#BB4045", linewidth=0.85, linestyle="--", alpha=0.8)
    axis.set_xlim(start, stop)
    axis.set_ylim(-0.05, 13.6)
    axis.set_yticks(positions, labels)
    axis.tick_params(axis="y", length=0, pad=12)
    axis.set_xlabel("Recorded CPU rising-edge index within this 1024-edge window", labelpad=10)
    axis.grid(axis="x", color="#E2E7ED", linewidth=0.6)
    if stop - start <= 64:
        axis.set_xticks(np.arange(start, stop + 1, max(1, (stop - start) // 16)))
    for spine in ("top", "right", "left"):
        axis.spines[spine].set_visible(False)
    secondary = axis.secondary_xaxis("top", functions=(lambda value: value - trigger,
                                                         lambda value: value + trigger))
    secondary.set_xlabel("CPU rising edges relative to first recorded capture predicate", labelpad=8)
    figure.text(0.145, 0.065,
                f"ID / EX / MEM held cycles: {checks['id_held_cycles']} / {checks['ex_held_cycles']} / "
                f"{checks['mem_held_cycles']} | MEM flush cycles: {checks['mem_flush_cycles']} | "
                f"CSV SHA256 {receipt['raw_sha256'][:16]}...", fontsize=9, color="#354254")
    source_label = ("Source: synthetic test fixture." if prefix == "SYNTHETIC OFFLINE FIXTURE"
                    else "Source: recorded local RTL signals.")
    figure.text(0.145, 0.035,
                source_label + " Window event rates do not establish whole-run IPC or stall causality. Simulator time is separate from target FPGA frequency.",
                fontsize=9, color="#5E6978")
    result = {}
    for extension in ("png", "svg"):
        path = output / f"{stem}.{extension}"
        figure.savefig(path, dpi=180, facecolor="white")
        result[extension] = str(path)
    plt.close(figure)
    return result


LOCAL_SEMANTICS = ("if_valid", "id_valid", "ex_valid", "mem_valid", "wb_valid",
                   "id_fire", "ex_fire", "mem_flush", "frontend_fire", "mem_fire")


def bound_path(manifest_path, value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (Path(manifest_path).parent / path).resolve()


def verify_simulation_receipt(manifest_path, manifest):
    run = bound_path(manifest_path, manifest["simulation_run_directory"])
    identity_path = run / "SOURCE_IDENTITY.json"
    identity = read_json(identity_path)
    if (identity.get("release") != manifest["release"] or identity.get("origin") != "LOCAL RTL SIMULATION"
            or identity.get("functional_rtl_edits") != 0 or identity.get("simulation_only_observation_port_bits") != 42):
        raise CaptureError("Simulation source identity differs from the declared local recording")
    if identity.get("source_inputs") != manifest["source_inputs"]:
        raise CaptureError("Capture manifest and simulation source identity differ")
    actual_inputs = []
    for role in ("observer", "driver"):
        path = bound_path(manifest_path, manifest["simulation_" + role])
        require_hash(path, identity[role + "_sha256"], "Simulation " + role)
        actual_inputs.append({"role": role, "path": str(path), "sha256": sha256(path)})
    firmware = run / "firmware.hex"
    require_hash(firmware, manifest["firmware_sha256"], "Simulated firmware image")
    require_hash(firmware, identity["firmware_sha256"], "Simulation identity firmware")
    actual_inputs.append({"role": "firmware", "path": str(firmware), "sha256": sha256(firmware)})
    rtl_checked = 0
    for source in manifest["source_inputs"]:
        source_path = bound_path(manifest_path, source["path"])
        if source_path.parent.name == "rtl":
            actual = run / "inputs" / "rtl" / source_path.name
            require_hash(actual, source["sha256"], "Simulated RTL copy")
            rtl_checked += 1
    if not rtl_checked:
        raise CaptureError("Simulation source identity contains no RTL inputs")
    commands = {}
    for name in ("compile", "simulate"):
        path = run / (name + ".command.json")
        command = read_json(path)
        if command.get("exit_code") != 0:
            raise CaptureError("Local simulation " + name + " has no successful process receipt")
        commands[name] = {"path": str(path), "sha256": sha256(path), "exit_code": 0}
    stdout = run / "simulate.stdout.log"
    log = stdout.read_text(encoding="utf-8-sig")
    match = re.search(r"LOCAL_RTL_CAPTURE_PASS cycles=(\d+) cycle_count=(\d+) retired=(\d+)", log)
    if not match or int(match[1]) != manifest["cycle_limit"] or int(match[2]) != manifest["cycle_limit"]:
        raise CaptureError("Local capture log has no complete declared observation run")
    for window in manifest["windows"]:
        expected = f"CAPTURE_WINDOW_PASS function={window['function']} samples=1024 trigger_sample=256"
        if expected not in log:
            raise CaptureError("Local capture log is missing a recorded function window")
    # Bind every simulator input retained in the actual compile directory, including
    # native memory models. The RTL copies above must match the frozen build sources.
    inputs = [{"path": str(path), "sha256": sha256(path)}
              for path in sorted((run / "inputs").rglob("*")) if path.is_file()]
    return {"source_identity": str(identity_path), "source_identity_sha256": sha256(identity_path),
            "recording_driver_inputs": actual_inputs, "all_simulator_inputs": inputs,
            "frozen_rtl_files_verified": rtl_checked, "processes": commands,
            "capture_stdout": str(stdout), "capture_stdout_sha256": sha256(stdout),
            "observation_run_cpu_edges": int(match[1]), "observation_run_retired": int(match[3])}


def read_recorded_vcd(path):
    """Read settled timestamp groups and select the recorded rising-edge values."""
    text = Path(path).read_text(encoding="utf-8-sig")
    header, separator, changes = text.partition("$enddefinitions $end")
    if not separator:
        raise CaptureError("VCD is missing its enddefinitions marker")
    scale_match = re.search(r"\$timescale\s+(\d+)\s*(s|ms|us|ns|ps|fs)\s+\$end", header)
    if not scale_match:
        raise CaptureError("VCD timescale is missing or unsupported")
    unit_ps = {"s": Decimal("1e12"), "ms": Decimal("1e9"), "us": Decimal("1e6"),
               "ns": Decimal("1000"), "ps": Decimal("1"), "fs": Decimal("0.001")}
    tick_ps = Decimal(scale_match[1]) * unit_ps[scale_match[2]]
    variables = {}
    code_width = {}
    for match in re.finditer(r"\$var\s+\S+\s+(\d+)\s+(\S+)\s+([^\n]*?)\s+\$end", header):
        width, code = int(match[1]), match[2]
        reference = match[3].split()[0]
        reference = re.sub(r"\[\d+:\d+\]$", "", reference).rsplit("/", 1)[-1].rsplit(".", 1)[-1].lower()
        if reference in variables:
            raise CaptureError("Duplicate selected VCD reference: " + reference)
        variables[reference] = (code, width)
        code_width[code] = width
    required = ("cpu_clk", "ex_pc") + LOCAL_SEMANTICS
    if any(name not in variables for name in required):
        raise CaptureError("VCD is missing one of the recorded42-bit probe signals")
    if variables["ex_pc"][1] != 32 or any(variables[name][1] != 1 for name in required if name != "ex_pc"):
        raise CaptureError("VCD probe widths differ from the42-bit layout")
    state = {}
    rows, times_ps, cycles, predicates = [], [], [], []
    timestamp = 0
    previous_clock = None

    def value(name):
        code, width = variables[name]
        binary = state.get(code)
        if binary is None or any(bit not in "01" for bit in binary):
            raise CaptureError("VCD has an unknown or absent sampled value: " + name)
        number = int(binary, 2)
        if number >= 1 << width:
            raise CaptureError("VCD value exceeds its declared width")
        return number

    def flush():
        nonlocal previous_clock
        clock_code = variables["cpu_clk"][0]
        current = state.get(clock_code)
        if previous_clock == "0" and current == "1":
            pc = value("ex_pc")
            rows.append([(pc >> bit) & 1 for bit in range(32)] + [value(name) for name in LOCAL_SEMANTICS])
            times_ps.append(Decimal(timestamp) * tick_ps)
            cycle_name = next((name for name in ("cycle", "cyclecounter", "cycle_counter") if name in variables), None)
            cycles.append(value(cycle_name) if cycle_name else None)
            predicates.append(value("trigger") if "trigger" in variables else None)
        previous_clock = current

    for line in changes.splitlines():
        line = line.strip()
        if not line or line.startswith("$"):
            continue
        if line.startswith("#"):
            flush()
            try:
                following = int(line[1:])
            except ValueError:
                raise CaptureError("Malformed VCD timestamp") from None
            if following < timestamp:
                raise CaptureError("VCD timestamps are out of order")
            timestamp = following
        elif line[0].lower() == "b":
            parts = line[1:].split()
            if len(parts) != 2 or parts[1] not in code_width:
                raise CaptureError("Malformed VCD vector value")
            state[parts[1]] = parts[0].lower()
        elif line[0].lower() in "01xz":
            code = line[1:]
            if code not in code_width:
                raise CaptureError("VCD value references an undeclared variable")
            state[code] = line[0].lower()
        else:
            raise CaptureError("Unsupported VCD value record")
    flush()
    if len(rows) != 1024:
        raise CaptureError(f"VCD contains {len(rows)} rising-edge samples; expected1024")
    differences = [times_ps[index + 1] - times_ps[index] for index in range(1023)]
    if len(set(differences)) != 1 or differences[0] <= 0:
        raise CaptureError("VCD rising edges are not a contiguous constant-period window")
    return rows, times_ps, cycles, predicates, {"timescale": scale_match[0],
            "rising_edge_period_ps": str(differences[0]), "selected_samples": len(rows)}


def verify_local_window(manifest_path, window):
    manifest_path = Path(manifest_path).resolve()
    manifest = read_json(manifest_path)
    if manifest.get("origin") != "LOCAL RTL SIMULATION":
        raise CaptureError("Waveform manifest must explicitly identify LOCAL RTL SIMULATION")
    sources = manifest.get("source_inputs")
    if not isinstance(sources, list) or not sources:
        raise CaptureError("Waveform manifest has no bound simulation source inputs")
    for source in sources:
        require_hash(bound_path(manifest_path, source["path"]), source["sha256"], "Simulation source input")
    simulator = verify_simulation_receipt(manifest_path, manifest)
    elf = bound_path(manifest_path, manifest["elf"]["path"])
    require_hash(elf, manifest["elf"]["sha256"], "Recorded simulation ELF")
    symbols = read_elf_symbols(elf)
    mapping_path = bound_path(manifest_path, manifest["mapping_audit"]["path"])
    require_hash(mapping_path, manifest["mapping_audit"]["sha256"], "Recorded probe mapping")
    mapping = read_json(mapping_path)
    channels = sorted(mapping["data"], key=lambda item: item["channel"])
    if len(channels) != 42 or [item["channel"] for item in channels] != list(range(42)):
        raise CaptureError("Recorded mapping does not contain exactly42 ordered probes")
    names = [item["native"] for item in channels]
    if [item["meaning"] for item in channels] != [f"ex_pc[{bit}]" for bit in range(32)] + list(LOCAL_SEMANTICS):
        raise CaptureError("Recorded probe semantic mapping differs from the declared42-bit layout")
    csv_path, vcd_path = bound_path(manifest_path, window["csv"]), bound_path(manifest_path, window["vcd"])
    require_hash(csv_path, window["csv_sha256"], "Recorded CSV")
    require_hash(vcd_path, window["vcd_sha256"], "Recorded VCD")
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        csv_records = list(csv.reader(stream))
    if not csv_records:
        raise CaptureError("Recorded CSV is empty")
    header = csv_records[0]
    if header[:43] != ["Sample"] + names or len(set(header)) != len(header):
        raise CaptureError("Local CSV header does not preserve the exact42 native probe names")
    extras = header[43:]
    if "Cycle" not in extras or "Trigger" not in extras or any(name not in ("Cycle", "Trigger", "SimTimePs", "SimTimeNs") for name in extras):
        raise CaptureError("Local CSV metadata columns differ from the documented window schema")
    if len(csv_records) != 1025 or window.get("samples") != 1024:
        raise CaptureError("Local waveform must contain exactly1024 recorded samples")
    rows, cycles, predicates, timestamps = [], [], [], []
    for index, record in enumerate(csv_records[1:]):
        if len(record) != len(header) or record[0] != str(index) or any(bit not in ("0", "1") for bit in record[1:43]):
            raise CaptureError("Local CSV contains reordered, missing or nonbinary probe samples")
        metadata = dict(zip(extras, record[43:]))
        if not metadata["Cycle"].isdigit() or metadata["Trigger"] not in ("0", "1"):
            raise CaptureError("Local cycle/predicate metadata is malformed")
        cycle = int(metadata["Cycle"])
        if cycles and cycle != cycles[-1] + 1:
            raise CaptureError("Local CSV omits or duplicates a CPU rising edge")
        rows.append([int(bit) for bit in record[1:43]])
        cycles.append(cycle)
        predicates.append(int(metadata["Trigger"]))
        if "SimTimePs" in metadata:
            timestamps.append(Decimal(metadata["SimTimePs"]))
        elif "SimTimeNs" in metadata:
            timestamps.append(Decimal(metadata["SimTimeNs"]) * 1000)
    vcd_rows, vcd_times, vcd_cycles, vcd_predicates, vcd_info = read_recorded_vcd(vcd_path)
    if rows != vcd_rows:
        raise CaptureError("One or more of the43008 CSV probe bits differ from recorded VCD rising edges")
    if any(value is not None for value in vcd_cycles) and vcd_cycles != cycles:
        raise CaptureError("VCD and CSV absolute CPU edge counters differ")
    if any(value is not None for value in vcd_predicates) and vcd_predicates != predicates:
        raise CaptureError("VCD and CSV capture predicates differ")
    if timestamps and timestamps != vcd_times:
        raise CaptureError("VCD and CSV actual simulator timestamps differ")
    raw_path = bound_path(manifest_path, window["raw_csv"])
    require_hash(raw_path, window["raw_csv_sha256"], "Original packed RTL observations")
    with raw_path.open(encoding="utf-8-sig", newline="") as stream:
        raw_records = list(csv.reader(stream))
    if len(raw_records) != 1025 or raw_records[0] != ["Cycle", "SimTimePs", "Data"]:
        raise CaptureError("Original packed RTL observations have an unexpected schema")
    for index, raw in enumerate(raw_records[1:]):
        if len(raw) != 3:
            raise CaptureError("Original packed RTL observation is incomplete")
        cycle, time_ps, packed = int(raw[0]), Decimal(raw[1]), int(raw[2])
        if (cycle != cycles[index] or time_ps != vcd_times[index] or packed < 0 or packed >= 1 << 42
                or packed != sum(bit << bit_index for bit_index, bit in enumerate(rows[index]))):
            raise CaptureError("Original packed RTL observation differs from its CSV/VCD expansion")
    decoded_path = bound_path(manifest_path, window["decoded_csv"])
    require_hash(decoded_path, window["decoded_csv_sha256"], "Recorded decoded CSV")
    with decoded_path.open(encoding="utf-8-sig", newline="") as stream:
        decoded = list(csv.reader(stream))
    if len(decoded) != 1025 or decoded[0] != ["Sample", "Cycle", "SimTimePs", "EX_PC"] + list(LOCAL_SEMANTICS) + ["Trigger"]:
        raise CaptureError("Recorded decoded CSV has an unexpected schema")
    for index, values in enumerate(decoded[1:]):
        expected = ([str(index), str(cycles[index]), str(vcd_times[index]),
                     f"0x{sum(rows[index][bit] << bit for bit in range(32)):08x}"]
                    + [str(bit) for bit in rows[index][32:42]] + [str(predicates[index])])
        if values != expected:
            raise CaptureError("Decoded semantic CSV differs from its native-bit recordings")
    if window.get("first_cycle", cycles[0]) != cycles[0] or window.get("last_cycle", cycles[-1]) != cycles[-1]:
        raise CaptureError("Local source manifest and CSV edge boundaries differ")
    trigger_pc = window["trigger_pc"]
    trigger_pc = int(trigger_pc, 0) if isinstance(trigger_pc, str) else trigger_pc
    trigger = window["trigger_sample"]
    if type(trigger) is not int or not 0 <= trigger < 1024 or not predicates[trigger]:
        raise CaptureError("Declared capture predicate sample was not recorded")
    rows_with_predicate = [row + [predicate] for row, predicate in zip(rows, predicates)]
    checks = validate_pipeline(rows_with_predicate, trigger_pc, channel40_semantic="frontend_fire")
    if checks["trigger_matching_indices"][0] != trigger:
        raise CaptureError("First observed capture predicate differs from the declared trigger edge")
    if function_at(trigger_pc, symbols) != window["function"]:
        raise CaptureError("Capture predicate PC does not belong to the declared exact ELF function")
    checks["mem_fire_events"] = sum(row[41] for row in rows)
    checks["pipeline_occupied_cycles"] = {name: sum(row[32 + index] for row in rows)
                                           for index, name in enumerate(LOCAL_SEMANTICS[:5])}
    receipt = {"variant": manifest["release"], "configured_clock_hz": manifest["clock_hz"],
               "checks": checks, "alignment": {"first_aligned_trigger_index": trigger},
               "raw_sha256": window["csv_sha256"], "source_csv_sha256": window["csv_sha256"],
               "source_vcd_sha256": window["vcd_sha256"], "samples": 1024}
    origin = {"kind": "LOCAL RTL SIMULATION", "hardware_validated": False,
              "waveform_manifest": str(manifest_path), "waveform_manifest_sha256": sha256(manifest_path),
              "csv": str(csv_path), "vcd": str(vcd_path), "elf": str(elf), "elf_sha256": sha256(elf),
              "mapping_audit": str(mapping_path), "mapping_audit_sha256": sha256(mapping_path),
              "simulation_clock_hz": manifest.get("simulation_clock_hz"), "uart_baud": manifest.get("uart_baud"),
              "vcd_clock": vcd_info, "first_absolute_cycle": cycles[0], "last_absolute_cycle": cycles[-1],
              "every_csv_probe_bit_verified_against_vcd": True,
              "source_inputs_verified": len(sources),
              "original_packed_csv": str(raw_path), "original_packed_csv_sha256": sha256(raw_path),
              "packed_observations_to_csv_every_bit_verified": True,
              "decoded_csv": str(decoded_path), "decoded_csv_sha256": sha256(decoded_path),
              "simulator": simulator,
              "sampling_semantics": manifest.get("sampling_semantics", "Recorded RTL values associated with the consuming CPU rising edge")}
    return receipt, rows_with_predicate, symbols, origin


def render_local_window(manifest_path, window, *, output=None, zoom_length=32):
    if not 8 <= zoom_length <= 128:
        raise CaptureError("Zoom length must be between 8 and 128 recorded edges")
    receipt, rows, symbols, origin = verify_local_window(manifest_path, window)
    destination = Path(output).resolve() if output else Path(manifest_path).parent / "analysis" / window["function"]
    destination.mkdir(parents=True, exist_ok=True)
    trigger = receipt["alignment"]["first_aligned_trigger_index"]
    zoom_start = max(0, min(1024 - zoom_length, trigger - zoom_length // 4))
    full = plot_window(receipt, rows, symbols, origin, destination, stem="full1024")
    zoom = plot_window(receipt, rows, symbols, origin, destination, start=zoom_start, length=zoom_length, stem="trigger-zoom")
    counts = Counter(function_at(sum(row[bit] << bit for bit in range(32)), symbols) for row in rows if row[38])
    report = {"schema": 1, "origin": origin, "release": receipt["variant"], "function": window["function"],
              "renderer": {"path": str(Path(__file__).resolve()), "sha256": sha256(__file__)},
              "rendered_utc": utc_now(), "samples": 1024, "channels": 42,
              "source_csv_sha256": receipt["source_csv_sha256"], "source_vcd_sha256": receipt["source_vcd_sha256"],
              "source_values_filled_or_inferred": False, "configured_fpga_clock_hz": receipt["configured_clock_hz"],
              "x_axis": "Actual recorded CPU rising-edge index; not physical FPGA elapsed time",
              "checks": receipt["checks"], "ex_fire_function_counts": dict(counts.most_common()),
              "full": full, "zoom": zoom, "zoom_start": zoom_start, "zoom_length": zoom_length,
              "output_sha256": {Path(path).name: sha256(path) for group in (full, zoom) for path in group.values()}}
    write_json(destination / "waveform-analysis.json", report)
    if read_json(destination / "waveform-analysis.json") != report:
        raise CaptureError("Rendered waveform receipt did not reopen unchanged")
    from PIL import Image
    for group in (full, zoom):
        with Image.open(group["png"]) as image:
            image.verify()
        svg = Path(group["svg"]).read_text(encoding="utf-8")
        if "<svg" not in svg or "LOCAL RTL SIMULATION" not in svg:
            raise CaptureError("Local RTL plot source label verification failed")
    return report


def render_local_manifest(manifest_path, *, zoom_length=32):
    manifest = read_json(manifest_path)
    expected = {"core_bench_list", "core_bench_matrix", "core_bench_state"}
    windows = manifest.get("windows", [])
    if len(windows) != 3 or {window.get("function") for window in windows} != expected:
        raise CaptureError("The release needs one actual window for each of its three CoreMark kernels")
    return [render_local_window(manifest_path, window, zoom_length=zoom_length) for window in windows]


def write_local_aggregate(root, reports):
    root = Path(root).resolve()
    destination = root / "analysis"
    destination.mkdir(parents=True, exist_ok=True)
    releases = {"Original_155250", "H3_Base_145125", "H3_Retained_145125"}
    if len(reports) != 9 or {report["release"] for report in reports} != releases:
        raise CaptureError("Aggregate needs all nine actual local RTL windows across the three requested cores")
    aggregate = {"schema": 1, "origin": "LOCAL RTL SIMULATION", "hardware_waveform_claim": False,
                 "generated_utc": utc_now(), "windows": reports,
                 "total_recorded_edges": sum(report["samples"] for report in reports),
                 "csv_vcd_probe_bits_checked": sum(report["samples"] * report["channels"] for report in reports),
                 "whole_run_ipc_claim": False, "physical_elapsed_time_claim": False,
                 "remote_platform_status": "unused; local RTL recordings selected by user"}
    write_json(destination / "WAVEFORM_ANALYSIS.json", aggregate)
    if read_json(destination / "WAVEFORM_ANALYSIS.json") != aggregate:
        raise CaptureError("Aggregate waveform receipt did not reopen unchanged")
    lines = ["# Local RTL simulation waveform recordings", "",
             "All nine windows contain 1024 consecutive CPU rising-edge observations from the selected RTL and firmware. Each 42-bit CSV is checked against its recorded VCD at every edge. The PNG and SVG views retain the label LOCAL RTL SIMULATION.", "",
             "The horizontal axis counts recorded CPU edges. Target FPGA frequency, actual simulator timestamps and accelerated UART settings are separate metadata. These local event counts describe the window and do not replace full-run CoreMark counters.", "",
             "| Core | Function | WB events /1024 | Local WB event rate | ID held | EX held | MEM held | Frontend transfers | MEM fire | MEM flush | Plots |", 
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for report in reports:
        checks = report["checks"]
        full = Path(report["full"]["png"]).relative_to(root).as_posix()
        zoom = Path(report["zoom"]["png"]).relative_to(root).as_posix()
        vcd = Path(report["origin"]["vcd"]).relative_to(root).as_posix()
        lines.append(f"| {report['release']} | {report['function']} | {checks['wb_events']} | "
                     f"{checks['local_retirement_event_rate']:.6f} | {checks['id_held_cycles']} | "
                     f"{checks['ex_held_cycles']} | {checks['mem_held_cycles']} | {checks['frontend_fire_events']} | "
                     f"{checks['mem_fire_events']} | {checks['mem_flush_cycles']} | "
                     f"[1024 edges](../{full}) / [32-edge zoom](../{zoom}) / [VCD](../{vcd}) |")
    lines.extend(["", "MEM flush counts the recorded late MEM flush signal. It does not count every early redirect or identify branch-prediction errors. ID/EX/MEM held counts mean valid and no corresponding fire at that edge; they do not assign a cause to the hold.", "",
                  "Each window also has editable SVG versions and a waveform-analysis.json receipt beside its PNGs. WAVEFORM_ANALYSIS.json binds all nine source manifests, input hashes, CSV/VCD cross-checks, function labels and rendering outputs."])
    (destination / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if (destination / "README.md").read_text(encoding="utf-8") != "\n".join(lines) + "\n":
        raise CaptureError("Waveform report did not reopen unchanged")
    return aggregate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", type=Path, help="One actual local RTL waveform manifest; repeat for all three cores")
    parser.add_argument("--all-root", type=Path, help="Render the three known release waveform manifests and aggregate all nine windows")
    parser.add_argument("--zoom-length", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        if not 8 <= args.zoom_length <= 128:
            raise CaptureError("Zoom length must be between8 and128 recorded edges")
        manifests = args.manifest or []
        if args.all_root:
            manifests = [args.all_root / release / "waveforms" / "WAVEFORM_MANIFEST.json"
                         for release in ("Original_155250", "H3_Base_145125", "H3_Retained_145125")]
        if not manifests:
            raise CaptureError("Provide --manifest or --all-root")
        reports = [report for manifest in manifests for report in render_local_manifest(manifest, zoom_length=args.zoom_length)]
        if args.all_root:
            write_local_aggregate(args.all_root, reports)
        print(json.dumps({"state": "RENDERED", "origin": "LOCAL RTL SIMULATION", "windows": len(reports),
                          "png_files": len(reports) * 2, "svg_files": len(reports) * 2}))
        return 0
    except (CaptureError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"state": "FAILED", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
