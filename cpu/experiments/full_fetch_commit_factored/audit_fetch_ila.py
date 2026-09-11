import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import audit_fetch_shorts as short_audit
import audit_fetch_regressions as regression_audit
from pds_report import parse_ila_reports

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "build/pds/20260911-095312-74f93c4b"
CLOCK_HZ = 153000000
inputs = short_audit.inputs
shared = inputs.parent_audit.shared
digest = inputs.digest
require = inputs.require
load = inputs.load


def binding(source=SOURCE, validation=False, scope=False):
    require(type(validation) is bool and type(scope) is bool and not (validation and scope), "Invalid physical firmware role")
    require(source.resolve().parent == (ROOT / "build/pds").resolve(), "Wrong clock physical project")
    record = inputs.audit_inputs()
    regressions = regression_audit.audit_regressions()
    shorts = short_audit.audit_shorts()
    inventory = record["physical_source_hashes"]
    shared.validate_inventory(load(source / "source-snapshot.json"), inventory, source)
    application = None
    if scope:
        from audit_fetch_scope_firmware import audit_firmware
        application = audit_firmware(source / "firmware.hex")
    else:
        firmware_name = "coremark_v" + str(int(validation)) + "_i6000_p2700000_f153000000_rv32gcc_rv32im_O3_unroll_relax.build.json"
        firmware = load(inputs.PARENT / "build" / firmware_name)
        require(digest(source / "firmware.hex") == firmware["HexSha256"] and firmware["ClockHz"] == CLOCK_HZ and
                firmware["ValidationRun"] is validation and firmware["Iterations"] == 6000, "Wrong 153 MHz physical firmware")
    parameters = inputs.parent_audit.binding()["hardware_parameters"]
    shared.validate_wrapper((source / "pds_soc_top.v").read_text(encoding="utf-8-sig"), parameters, CLOCK_HZ, source / "firmware.hex")
    require(('add_design "' + (source / "pds_soc_top.v").as_posix() + '"') in (source / "build.tcl").read_text(encoding="utf-8-sig"), "Physical wrapper not referenced")
    result = {"schema": 1, "scope": "complete 153 MHz source/parameter/firmware/short-run binding; not timing or score qualification",
            "source": str(source), "clock_hz": CLOCK_HZ, "physical_source_hashes": inventory, "hardware_parameters": parameters,
            "firmware_sha256": digest(source / "firmware.hex"), "regressions": regressions, "short_manifest_sha256": [run["manifest_sha256"] for run in shorts["runs"]]}
    if application is not None:
        result["application_firmware"] = application
    return result


def normalize_mapping(netlist, fic, output, probe):
    available = re.findall(r"^\d+\s*:\s*(\S+)\s+\S+\s*$", probe, re.M)
    soc_modules = re.findall(r"\bmodule rv32_soc\b(.*?)\bendmodule\b", netlist, re.S)
    require(len(soc_modules) == 1, "SoC module missing or ambiguous")
    instances = re.findall(r"\brv32_core\s+core\s*\((.*?)\);", soc_modules[0], re.S)
    require(len(instances) == 1, "CPU instance missing or ambiguous")
    aliases = {}
    local_fic, local_output = fic, output
    for index in range(4):
        local = "board/soc/core/pipeline_valid[" + str(index) + "]"
        outer = "board/soc/unused_pipeline_valid[" + str(index) + "]"
        selected = re.findall(r"^Project.unit<0>.dataChannel<" + str(32 + index) + r">=(.+)$", fic, re.M)
        require(len(selected) == 1, "Missing native pipeline channel")
        actual = selected[0].strip()
        require(actual in (local, outer) and available.count(actual) == 1, "Unverified or ambiguous pipeline alias")
        if actual == outer:
            connections = re.findall(r"\.pipeline_valid\s*\(\{([^}]+)\}\)", instances[0])
            require(len(connections) == 1, "Missing pipeline alias port connection")
            bits = [value.strip() for value in connections[0].split(",")]
            require(len(bits) == 5 and bits[4 - index] == "unused_pipeline_valid[" + str(index) + "]", "Wrong native pipeline alias connection")
            local_fic = local_fic.replace(outer, local)
            local_output = local_output.replace(outer, local)
        canonical = outer if index == 3 else local
        if actual != canonical:
            aliases[actual] = canonical
    wb_canonical = "board/soc/core/board/unused_trace_valid"
    wb_outer = "board/soc/unused_pipeline_valid[4]"
    selected = re.findall(r"^Project.unit<0>.dataChannel<36>=(.+)$", fic, re.M)
    require(len(selected) == 1, "Missing writeback-valid channel")
    wb_actual = selected[0].strip()
    require(wb_actual in (wb_canonical, wb_outer) and available.count(wb_actual) == 1, "Unverified or ambiguous writeback alias")
    core_modules = re.findall(r"\bmodule rv32_core\b(.*?)\bendmodule\b", netlist, re.S)
    require(len(core_modules) == 1, "CPU module missing or ambiguous")
    wb_pattern = (r"\bGTP_DFF_C\s*/\*\s*wb_valid\s*\*/\s*#\([^;]*?\)\s*wb_valid\s*\(\s*"
                  + r"\.Q\s*\(\\board/unused_trace_valid\s+\)")
    require(len(re.findall(wb_pattern, core_modules[0], re.S)) == 1, "Wrong writeback register driver")
    if wb_actual == wb_outer:
        port_pattern = r"\.\\board/unused_trace_valid\s+\(\s*unused_pipeline_valid\[4\]\s*\)"
        require(len(re.findall(port_pattern, instances[0])) == 1, "Wrong writeback alias connection")
        local_fic = local_fic.replace(wb_outer, wb_canonical)
        local_output = local_output.replace(wb_outer, wb_canonical)
        aliases[wb_outer] = wb_canonical
    canonical_fic, canonical_output, _ = shared.normalize_pipeline_mapping(netlist, local_fic, local_output)
    return canonical_fic, canonical_output, aliases


def mapping(stage, source=SOURCE, validation=False, scope=False):
    require(stage.resolve().parent == (ROOT / "build/ila").resolve(), "Wrong clock ILA workspace")
    bound = binding(source, validation, scope)
    copies = shared.validate_stage_inputs(stage, source)
    fic = (stage / "cpu-remapped.fic").read_text(encoding="utf-8-sig")
    paths = re.findall(r"^Project.device.designInputFile=(.+)$", fic, re.M)
    require(len(paths) == 1 and Path(paths[0].strip()).resolve() == (stage / "source.adf").resolve(), "Wrong Inserter ADF")
    require(not (stage / "probe.stderr.txt").read_text().strip() and not (stage / "verify-remapped.stderr.txt").read_text().strip(), "Inserter stderr is not empty")
    fic, output, aliases = normalize_mapping((stage / "netlist.v").read_text(encoding="utf-8-sig"), fic,
                                            (stage / "verify-remapped.stdout.txt").read_text(encoding="utf-8-sig"),
                                            (stage / "probe.stdout.txt").read_text(encoding="utf-8-sig"))
    result = shared.validate_config(fic, output)
    result.update(schema=1, aliases=aliases, binding=bound, clock_hz=CLOCK_HZ, source_build=str(source), full_score_qualified=False,
                  sha256={name: digest(stage / name) for name in (*copies, "cpu-remapped.fic", "verify-remapped.stdout.txt", "verify-remapped.stderr.txt", "probe.stdout.txt", "probe.stderr.txt", "probe.tcl")})
    destination = stage / "mapping-audit.json"
    content = json.dumps(result, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == content, "Clock mapping receipt changed")
    destination.write_text(content, encoding="utf-8")
    return result


def qualify(stage, source=SOURCE, placement_seed=1, validation=False, scope=False):
    mapped = mapping(stage, source, validation, scope)
    invocation = load(stage / "invocation.json")
    require(invocation["ExitCode"] == 0 and invocation["PlacementSeed"] == placement_seed, "PDS incomplete or wrong seed")
    require(Path(invocation["WorkingDirectory"]).resolve() == stage.resolve(), "Wrong physical working directory")
    started = datetime.fromisoformat(invocation["StartedUtc"]).timestamp()
    finished = datetime.fromisoformat(invocation["FinishedUtc"]).timestamp()
    require(finished >= started, "Invalid physical invocation interval")
    expected_inputs = {"source.adf", "netlist.v", "firmware.hex", "cpu-remapped.fic", "board.fdc", "uart_remotelab.fdc", "build.tcl", "mapping-audit.json"}
    require(set(invocation["Inputs"]) == expected_inputs, "Incomplete physical input inventory")
    for name, checksum in invocation["Inputs"].items():
        require(digest(stage / name) == checksum, "Physical input changed")
    outputs = {"timing": "report_timing/pds_soc_top.rtr", "log": "run.log", "bitstream": "generate_bitstream/pds_soc_top.sbit", "stdout": "pds.stdout.log", "stderr": "pds.stderr.log"}
    for name, relative in outputs.items():
        path = stage / relative
        require(path.is_file() and started - 2 <= path.stat().st_mtime <= finished + 2, "Output not from physical invocation")
        require(name == "stderr" or path.stat().st_size > 0, "Empty physical output")
    log = (stage / "run.log").read_text(encoding="utf-8-sig")
    messages = log + (stage / "pds.stdout.log").read_text(encoding="utf-8-sig") + (stage / "pds.stderr.log").read_text(encoding="utf-8-sig")
    require(not re.search(r"^\s*(?:E:|Error:)", messages, re.M), "PDS reported an error")
    commands = [line.strip() for line in (stage / "build.tcl").read_text().splitlines() if line.startswith("pnr")]
    require(commands == ["pnr -gplace_seed " + str(placement_seed)], "Unexpected placement command")
    report = parse_ila_reports((stage / outputs["timing"]).read_text(encoding="utf-8-sig"), log, CLOCK_HZ)
    report.update(schema=1, run_directory=str(stage), placement_seed=placement_seed,
                  physical_timing_passed=report["constraints_met"], resource_efficiency_qualified=False, hardware_validated=False,
                  full_score_qualified=False, coremark_score=None, source_binding=mapped["binding"],
                  ila={name: mapped[name] for name in ("data_channels", "trigger_channels", "depth", "clock")},
                  inputs_sha256=invocation["Inputs"], outputs_sha256={name: digest(stage / relative) for name, relative in outputs.items()})
    (stage / "physical-qualification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("binding", "mapping", "qualify"))
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--placement-seed", type=int, default=1)
    roles = parser.add_mutually_exclusive_group()
    roles.add_argument("--validation", action="store_true")
    roles.add_argument("--scope", action="store_true")
    arguments = parser.parse_args()
    if arguments.mode == "binding":
        result = binding(arguments.source, arguments.validation, arguments.scope)
    else:
        require(arguments.stage is not None, "Stage is required")
        result = mapping(arguments.stage, arguments.source, arguments.validation, arguments.scope) if arguments.mode == "mapping" else qualify(arguments.stage, arguments.source, arguments.placement_seed, arguments.validation, arguments.scope)
    print(json.dumps(result, indent=2))
    if arguments.mode == "qualify":
        raise SystemExit(0 if result["physical_timing_passed"] else 2)
