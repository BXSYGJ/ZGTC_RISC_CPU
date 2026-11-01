"""Inventory actual exported physical sites; retain unattributed cells explicitly."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

OUTPUTS = {"V_LUT6CARRY": {"COUT", "Z", "Z5"}, "V_RAM64X1": {"RDO"}, "V_RAM32X2": {"RDO"},
           "V_FFASYN": {"Q"}, "V_FFSYN": {"Q"}, "V_INV": {"Z"}, "V_BUF": {"Z"},
           "V_MUX2": {"Z"}, "V_USCM": {"CLKOUT"}, "V_IBUF": {"O"}, "V_OBUFT": {"O"}}


def nets(expression):
    if '"' in expression:
        return []
    return re.findall(r"\\[^\s,{}()]+|(?<![A-Za-z0-9_'\\])[A-Za-z_]\w*(?:\[\s*\d+(?::\d+)?\s*\])?", expression)


def trace_constants(cells):
    consumers = defaultdict(set)
    for index, cell in enumerate(cells):
        for port, expression in cell["ports"].items():
            if port not in OUTPUTS.get(cell["kind"], set()):
                for net in nets(expression):
                    consumers[net].add(index)
    result = []
    for index, cell in enumerate(cells):
        if cell["resource"] != "LUT6" or not re.fullmatch(r"(?:GND|VCC)_\d+/[^/]+/LUT6CARRY", cell["provenance"]):
            continue
        expected = "0" if cell["provenance"].startswith("GND_") else "1"
        if cell["parameters"].get("INIT") != "64'b" + expected * 64:
            raise ValueError("Generated constant site does not have the matching actual LUT INIT")
        queue = list(nets(cell["ports"]["Z"]))
        seen = set()
        terminals = set()
        visited_cells = set()
        unresolved = []
        while queue:
            net = queue.pop()
            if net in seen:
                continue
            seen.add(net)
            for consumer_index in consumers[net] - {index}:
                if consumer_index in visited_cells:
                    continue
                visited_cells.add(consumer_index)
                consumer = cells[consumer_index]
                if consumer["region"] in ("core", "fixture"):
                    terminals.add(consumer["region"])
                elif consumer["kind"] in OUTPUTS:
                    for port in OUTPUTS[consumer["kind"]]:
                        queue += nets(consumer["ports"].get(port, ""))
                else:
                    unresolved.append(consumer["physical_instance"])
        category = "shared" if terminals == {"core", "fixture"} else "core_only" if terminals == {"core"} else "fixture_only" if terminals == {"fixture"} else "no_owned_consumer"
        if unresolved:
            category = "unresolved"
        result.append({"physical_instance": cell["physical_instance"], "provenance": cell["provenance"],
                       "output_nets": nets(cell["ports"]["Z"]), "category": category,
                       "reached_regions": sorted(terminals), "unresolved_consumers": unresolved,
                       "reached_cells": [{key: cells[consumer][key] for key in ("kind", "physical_instance", "provenance", "region")}
                                         for consumer in sorted(visited_cells)]})
    return result


def report_totals(path):
    text = path.read_text(encoding="utf-8-sig")
    start = text.index("Device Utilization Summary :")
    stop = text.index("Global Clock Info:", start)
    table = text[start:stop]
    rows = re.findall(r"(?m)^\|\s+(FF|LUT|Distributed RAM)\s+\|\s+(\d+)\s+\|", table)
    totals = {key: sum(int(value) for name, value in rows if name == key) for key in ("LUT", "FF", "Distributed RAM")}
    module_start = text.index("Device Utilization Summary Of Each Module:")
    top = re.search(r"(?m)^\| bare_core_scan_top\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|", text[module_start:])
    core = re.search(r"(?m)^\|\s+\+ core_boundary\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(\d+)\s+\|", text[module_start:])
    if not top or not core:
        raise ValueError("Expected preserved core boundary in the actual final route report")
    categories = {}
    for kind in ("CLMA", "CLMS"):
        section = re.search(r"\| Use of " + kind + r"\s+\|[^\r\n]+[\s\S]*?(?=\| Use of |$)", table)
        if section is None:
            raise ValueError("Missing physical site-class resource table")
        categories[kind] = {name: int(value) for name, value in
                            re.findall(r"(?m)^\|\s+(FF|LUT|Distributed RAM)\s+\|\s+(\d+)\s+\|", section[0])}
    return {"global": totals, "physical_site_classes": categories,
            "hierarchy_top": dict(zip(("LUT", "FF", "Distributed RAM", "APM"), map(int, top.groups()))),
            "hierarchy_core": dict(zip(("LUT", "FF", "Distributed RAM", "APM"), map(int, core.groups()))),
            "path": str(path), "sha256": sha(path)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind_build(netlist):
    build = netlist.parents[2]
    manifest_path = build / "manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    source_path = Path(manifest["source_manifest"])
    if sha(source_path) != manifest["source_manifest_sha256"]:
        raise ValueError("Physical build source manifest identity changed")
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if manifest["parameters"] != source["parameters"] or manifest["functional_rtl_changes"] != 0:
        raise ValueError("Physical build changed the agreed core parameters or RTL")
    inputs = build / "inputs"
    if len([path for path in inputs.rglob("*") if path.is_file()]) != len(manifest["input_hashes"]):
        raise ValueError("Physical build input inventory changed")
    for relative, expected in manifest["input_hashes"].items():
        if sha(inputs / relative) != expected:
            raise ValueError("Physical build input hash changed: " + relative)
    closure = []
    if len(source["rtl"]) != 8:
        raise ValueError("Expected the exact eight-file pure core closure")
    for item in source["rtl"]:
        path = inputs / "rtl" / item["name"]
        if sha(path) != item["sha256"]:
            raise ValueError("Actual physical core RTL does not join the frozen source: " + item["name"])
        closure.append({"name": item["name"], "actual_physical_input": str(path), "sha256": item["sha256"]})
    if sha(inputs / "rv32_bare_core.sv") != source["wrapper"]["sha256"]:
        raise ValueError("Actual physical core wrapper differs from the extracted wrapper")
    return {"build_directory": str(build), "manifest": str(manifest_path), "manifest_sha256": sha(manifest_path),
            "release": manifest["release"], "observed_build_status": manifest["status"],
            "observed_build_stage": manifest["stage"], "clock_hz": manifest["clock_hz"],
            "fixture_profile": manifest.get("fixture_profile", "Initial"), "placement_seed": manifest["placement_seed"],
            "source_manifest": str(source_path), "source_manifest_sha256": sha(source_path),
            "core_source_joins": closure, "parameters": source["parameters"],
            "functional_rtl_changes": 0, "resource_inventory_does_not_assert_timing_acceptance": True}


def inspect(path):
    text = path.read_text(encoding="utf-8-sig")
    starts = list(re.finditer(r"(?m)^\s+(V_[A-Za-z0-9_]+)\s", text))
    cells = []
    for index, start in enumerate(starts):
        block = text[start.start():starts[index + 1].start() if index + 1 < len(starts) else len(text)]
        owner = re.search(r"/\*\s*(.*?)\s*\*/", block)
        name = re.search(r"(?m)^\s*\\([^\s]+)\s+\(", block)
        if not name:
            name = re.search(r"\b(V_[A-Za-z0-9_]+)\s+\\([^\s]+)\s+\(", block)
            instance = name[2] if name else None
        else:
            instance = name[1]
        if instance is None:
            plain = re.search(r"\bV_[A-Za-z0-9_]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", block)
            instance = plain[1] if plain else None
        if instance is None:
            raise ValueError("Missing physical instance name: " + block[:150])
        connection_start = re.search(r"(?:\\[^\s]+|GRS_INST)\s+\(", block)
        if not connection_start:
            raise ValueError("Missing physical connection block")
        fields = lambda value: dict(re.findall(r"\.(\w+)\s*\(([^()]*)\)", value))
        parameters = fields(block[:connection_start.start()])
        ports = fields(block[connection_start.end():])
        provenance = owner[1] if owner else ""
        region = "core" if provenance.startswith("core_boundary/dut/") else "fixture" if provenance.startswith(("input_shift[", "active_inputs[", "output_shift[", "output_snapshot[", "scan_phase")) else "other"
        kind = start[1]
        if kind not in set(OUTPUTS) | {"V_APM_E2", "V_GRS"}:
            raise ValueError("Unrecognized physical primitive requires explicit classification: " + kind)
        resource = "LUT6" if kind == "V_LUT6CARRY" else "DistributedRAM" if kind in ("V_RAM64X1", "V_RAM32X2") else "FF" if kind in ("V_FFASYN", "V_FFSYN") else "APM" if kind == "V_APM_E2" else "other"
        locations = [{"path": match[1].strip(), "line": int(match[2])}
                     for match in re.finditer(r"//\s+([^\r\n]*?\.sv):(\d+)", block)]
        if (region == "other" and resource != "other" and
                any(location["path"].endswith("/inputs/bare_core_scan_top.sv") for location in locations)):
            region = "fixture"
        cells.append({"kind": kind, "physical_instance": instance, "provenance": provenance,
                      "region": region, "resource": resource,
                      "source_locations": locations,
                      "site_class": instance.split("_", 1)[0], "parameters": parameters, "ports": ports,
                      "block_sha256": hashlib.sha256(block.encode("utf-8")).hexdigest()})
    summary = {}
    for key in ("kind", "region", "resource", "site_class"):
        summary[key] = dict(Counter(cell[key] for cell in cells))
    summary["resource_by_region"] = {region: dict(Counter(cell["resource"] for cell in cells if cell["region"] == region)) for region in ("core", "fixture", "other")}
    summary["resource_by_site_class"] = {site: dict(Counter(cell["resource"] for cell in cells if cell["site_class"] == site)) for site in sorted({cell["site_class"] for cell in cells})}
    summary["other_LUT_owners"] = dict(Counter(cell["provenance"].split("/", 1)[0] for cell in cells if cell["region"] == "other" and cell["resource"] == "LUT6"))
    sites = ["/".join(cell["physical_instance"].split("/")[:2]) for cell in cells if cell["resource"] in ("LUT6", "DistributedRAM")]
    if len(sites) != len(set(sites)):
        raise ValueError("More than one LUT/RAM primitive occupies the same exported physical slot")
    constants = trace_constants(cells)
    summary["constant_site_consumer_categories"] = dict(Counter(cell["category"] for cell in constants))
    return {"schema": "native-physical-primitive-area-audit/v1", "source": str(path), "source_sha256": sha(path),
            "audit_script_sha256": sha(__file__), "summary": summary, "cells": cells,
            "physical_build_binding": bind_build(path),
            "constant_site_consumer_traces": constants,
            "interpretation": "Raw native physical simulation primitive inventory. Unattributed sites are retained; this inventory alone does not assign reserved/tool-created LUTs to the core."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--route-report", type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.netlist.resolve())
        if args.route_report:
            native = report_totals(args.route_report.resolve())
            summary = report["summary"]
            by_region = summary["resource_by_region"]
            hierarchy_core_lut = by_region["core"].get("LUT6", 0) + by_region["core"].get("DistributedRAM", 0)
            hierarchy_fixture_lut = by_region["fixture"].get("LUT6", 0) + by_region["fixture"].get("DistributedRAM", 0)
            exported_lut = summary["resource"]["LUT6"] + summary["resource"].get("DistributedRAM", 0)
            if (hierarchy_core_lut != native["hierarchy_core"]["LUT"] or
                    by_region["core"].get("FF", 0) != native["hierarchy_core"]["FF"] or
                    hierarchy_core_lut + hierarchy_fixture_lut != native["hierarchy_top"]["LUT"] or
                    summary["resource"]["FF"] != native["global"]["FF"]):
                raise ValueError("Exported hierarchy does not reconcile to the actual native table")
            if native["global"]["LUT"] < exported_lut:
                raise ValueError("Physical primitive count exceeds the final native LUT summary")
            site_residues = {}
            for site in ("CLMA", "CLMS"):
                exported = summary["resource_by_site_class"].get(site, {})
                actual = native["physical_site_classes"][site]
                if exported.get("FF", 0) != actual["FF"] or exported.get("DistributedRAM", 0) != actual.get("Distributed RAM", 0):
                    raise ValueError("Physical FF or distributed RAM site-class counts differ from the native table")
                difference = actual["LUT"] - exported.get("LUT6", 0) - exported.get("DistributedRAM", 0)
                if difference < 0:
                    raise ValueError("Exported LUT sites exceed the native site-class count")
                site_residues[site] = difference
            counts = summary["constant_site_consumer_categories"]
            residue = native["global"]["LUT"] - exported_lut
            core_lower = hierarchy_core_lut + counts.get("core_only", 0)
            other_lut = by_region["other"].get("LUT6", 0) - len(report["constant_site_consumer_traces"])
            upper = core_lower + counts.get("shared", 0) + counts.get("unresolved", 0) + counts.get("no_owned_consumer", 0) + residue + other_lut
            report["native_report"] = native
            report["reconciliation"] = {"hierarchy_attributed_core_lut_including_ram": hierarchy_core_lut,
                "hierarchy_attributed_fixture_lut_including_ram": hierarchy_fixture_lut,
                "exported_tool_constant_lut_sites": len(report["constant_site_consumer_traces"]),
                "exported_other_lut_sites": other_lut,
                "global_lut_slots_not_present_in_export": residue,
                "global_lut_slot_residue_by_site_class": site_residues,
                "global_lut_count": native["global"]["LUT"], "exported_lut_and_ram_sites": exported_lut,
                "ff_exact": True, "native_hierarchy_exact": True,
                "core_lut_with_generated_overhead_lower_bound": core_lower,
                "core_lut_with_generated_overhead_upper_bound": upper,
                "bounds_interpretation": "Lower adds only constants whose reachable owned consumers are exclusively core. Upper assigns all shared/unresolved/unexported LUT overhead to core. Fixture-only constants stay outside both. Native hierarchy LUT area is separately exact."}
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if json.loads(args.output.read_text(encoding="utf-8")) != report:
            raise ValueError("Inventory reopening failed")
        print(json.dumps({key: value for key, value in report["summary"].items() if key != "other_LUT_owners"}, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print("NATIVE_EXPORT_INVENTORY_FAIL " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
