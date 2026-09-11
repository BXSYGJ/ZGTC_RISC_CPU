import json
import re
from pathlib import Path

from prepare_physical import digest, require

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_return_stack_link"
OLD = PARENT / "build/physical-project-complete/build/pds/20260911-035000-1d9fd437"
NEW = ROOT / "build/physical-project-complete/build/pds/20260911-041355-3d1b7a0e"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hierarchy(text, module):
    headers = [line for line in text.splitlines() if line.startswith("| Module Inst Name")]
    rows = [line for line in text.splitlines() if re.match(r"^\|\s*\+ " + re.escape(module) + r"\s*\|", line)]
    require(len(headers) == 1 and len(rows) == 1, "Missing or ambiguous synthesis hierarchy")
    columns = [value.strip() for value in headers[0].split("|")[1:] if value.strip()]
    values = [value.strip() for value in rows[0].split("|")[1:] if value.strip()]
    require(len(columns) == len(values), "Hierarchy column count mismatch")
    return {name: int(values[columns.index(name)]) for name in ("LUT", "FF", "LUT CARRY")}


def validate_source(root, source, project_name):
    staging = read_json(root / "build" / (project_name + "-inputs.json"))
    project = root / "build" / project_name
    require(Path(staging["project"]).resolve() == project.resolve(), "Wrong staged project")
    snapshot = read_json(source / "source-snapshot.json")
    require(Path(snapshot["Root"]).resolve() == (source / "source").resolve(), "Wrong captured source root")
    require(snapshot["Files"] == staging["source_hashes"] and len(snapshot["Files"]) == 20, "Incomplete physical inventory")
    for relative, expected in snapshot["Files"].items():
        current = root / Path(relative).name if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv") else ROOT.parent / "full_redirect_clock151200" / relative
        require(digest(current) == digest(project / relative) == digest(source / "source" / relative) == expected, "Physical input changed: " + relative)
    require("Executing : synthesize -ads -selected_syn_tool_opt 2 successfully." in (source / "run.log").read_text(encoding="utf-8-sig"), "Synthesis completion not proven")
    return staging


def relation_registers(text):
    result = {}
    for bit in range(3):
        name = "\\raw_pair_relation[" + str(bit) + "]"
        pattern = r"(GTP_DFF_[A-Z]+)\s+/\*\s*" + re.escape(name) + r"\s*\*/\s*#\((.*?)\)\s*" + re.escape(name) + r"\s+\((.*?)\);"
        matches = re.findall(pattern, text, re.S)
        require(len(matches) == 1, "Missing or duplicate relation register: " + str(bit))
        primitive, parameters, body = matches[0]
        pairs = re.findall(r"\.([A-Z_]+)\s*\(([^()]*)\)", body)
        ports = {name: value.strip() for name, value in pairs}
        require(len(ports) == len(pairs), "Duplicate relation register port")
        result[str(bit)] = {"primitive": primitive, "parameters": parameters.strip(), "ports": ports}
    return result


def validate_enable_removal(before_text, after_text):
    before, after = relation_registers(before_text), relation_registers(after_text)
    for bit in ("0", "1", "2"):
        old, new = before[bit], after[bit]
        old_kind, new_kind = ("GTP_DFF_PE", "GTP_DFF_P") if bit == "2" else ("GTP_DFF_CE", "GTP_DFF_C")
        require(old["primitive"] == old_kind and new["primitive"] == new_kind, "Wrong relation primitive transformation")
        require("CE" in old["ports"] and "CE" not in new["ports"], "Relation enable was not removed")
        require(set(old["ports"]) - {"CE"} == set(new["ports"]), "Unexpected relation port change")
        require(old["parameters"] == new["parameters"], "Relation reset initialization changed")
        for port in set(new["ports"]) - {"D"}:
            require(old["ports"][port] == new["ports"][port], "Relation clock/reset/output changed")
    return {"before": before, "after": after, "removed_clock_enables": 3}


def main():
    old = validate_source(PARENT, OLD, "physical-project-complete")
    new = validate_source(ROOT, NEW, "physical-project-complete")
    require(old["hardware_parameters"] == new["hardware_parameters"] and old["return_stack_depth"] == new["return_stack_depth"] == 2, "Hardware parameters differ")
    require({name for name, value in old["source_hashes"].items() if value != new["source_hashes"][name]} == {"rtl/rv32_core.sv"}, "Unexpected comparison delta")
    firmware_hash = digest(OLD / "firmware.hex")
    require(firmware_hash == digest(NEW / "firmware.hex") == "3A82C84E665E212C8BC8CF492CD169D7A579BF20146F810FA104F51EAE61287B", "Long firmware differs")
    old_wrapper = (OLD / "pds_soc_top.v").read_text(encoding="utf-8-sig").replace((OLD / "firmware.hex").as_posix(), "FIRMWARE")
    new_wrapper = (NEW / "pds_soc_top.v").read_text(encoding="utf-8-sig").replace((NEW / "firmware.hex").as_posix(), "FIRMWARE")
    require(old_wrapper == new_wrapper, "Native wrapper parameters differ")
    reports = [directory / "synthesize/pds_soc_top.snr" for directory in (OLD, NEW)]
    texts = [path.read_text(encoding="utf-8-sig") for path in reports]
    modules = {}
    for name in ("predictor", "core"):
        before, after = [hierarchy(text, name) for text in texts]
        modules[name] = {"before": before, "after": after, "change": {metric: after[metric] - before[metric] for metric in before}}
    netlists = [directory / "synthesize/pds_soc_top_syn.vm" for directory in (OLD, NEW)]
    registers = validate_enable_removal(*(path.read_text(encoding="utf-8-sig") for path in netlists))
    result = {"relation_registers": registers, "netlist_sha256": {str(path): digest(path) for path in netlists},
              "schema": 1, "scope": "source-bound synthesis hierarchy comparison; counts are not post-route LUTs and nested module totals must not be added",
              "old_run": str(OLD), "new_run": str(NEW), "clock_hz": 151200000, "modules": modules,
              "report_sha256": {str(path): digest(path) for path in reports}, "firmware_sha256": firmware_hash,
              "analyzer_sha256": digest(Path(__file__)), "full_system_resource_efficiency_qualified": False, "hardware_validated": False}
    (ROOT / "build/synthesis-comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
