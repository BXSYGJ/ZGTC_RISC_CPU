"""Isolated Windows ADS synthesis and full-ILA implementation, preserving every run."""
import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
from uuid import uuid4
import winreg

import run_embench as helper

ROOT = helper.ROOT
REFERENCE = helper.REFERENCE
PDS = Path("D:/PDS_2022.2-SP6.4/bin")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(path):
    return path.read_text(encoding="utf-8-sig")


def tcl_path(path):
    value = path.resolve().as_posix()
    require(not re.search(r'[{}"$;\r\n]', value), "Unsafe Tcl path")
    return "{" + value + "}"


def write_lines(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def original_function(path, name, namespace):
    """Reuse the exact audited function without importing historical run dependencies."""
    tree = ast.parse(text(path))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    require(len(nodes) == 1, "Missing historical audit function")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def invoke(executable, args, cwd, name, timeout):
    stdout, stderr = cwd / (name + ".stdout.log"), cwd / (name + ".stderr.log")
    record = {"argv": list(map(str, [executable]+args)), "working_directory": str(cwd),
              "executable_sha256": helper.sha(executable), "started_utc": datetime.now(timezone.utc).isoformat(),
              "exit_code": None, "timeout_seconds": timeout}
    receipt = cwd / (name + ".invocation.json")
    helper.write_json(receipt, record)
    with stdout.open("wb") as out, stderr.open("wb") as err:
        process = subprocess.Popen(record["argv"], cwd=cwd, stdout=out, stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        record["pid"] = process.pid; helper.write_json(receipt, record)
        print(f"{name} PID={process.pid} directory={cwd}", flush=True)
        try:
            record["exit_code"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Do not silently leave an orphaned implementation or delete its evidence.
            record["status"] = "timeout_process_still_running"
            helper.write_json(receipt, record)
            raise RuntimeError("PDS stage exceeded monitoring timeout; inspect PID before any further implementation")
        finally:
            record["finished_utc"] = datetime.now(timezone.utc).isoformat()
            helper.write_json(receipt, record)
    output = text(stdout) + text(stderr)
    require(record["exit_code"] == 0 and not re.search(r"^\s*(?:E:|Error:)", output, re.M), "Tool stage failed: " + name)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, choices=('priming_off', 'priming_on', 'accepted_valid_ram'))
    parser.add_argument("--workload", help="v25 board Embench workload, only with accepted")
    parser.add_argument("--firmware-run", required=True, type=Path)
    parser.add_argument("--configuration", choices=("V0", "V1"), default="V0")
    parser.add_argument("--seed", type=int, choices=(1,2,3), required=True)
    args = parser.parse_args()
    require(os.name == "nt", "Physical implementation requires Windows PDS")
    firmware_run = args.firmware_run.resolve()
    require(firmware_run.is_relative_to((ROOT / "results").resolve()), "Firmware must be in project results")
    firmware_manifest = json.loads(text(firmware_run / "manifest.json"))
    require(args.workload == "uart-loader", "v27 implements only the shared loader")
    is_embench = True
    if is_embench:
        require(firmware_manifest['status'] == 'built' and firmware_manifest['protocol'] in ('v25','v26'), 'Frozen board firmware required')
        require(firmware_manifest['protocol'] != 'v26' or args.workload == 'uart-loader', 'v26 implements the shared loader only')
    else:
        require(args.variant != 'accepted' and args.workload is None, 'Embench requires accepted plus workload')
        require(firmware_manifest["status"] in ("completed", "built_not_executed") and firmware_manifest["protocol"] in ("v4","v6"), "Frozen v4/v6 firmware required")
    clock_hz=firmware_manifest["configured_clock_hz"]
    require(clock_hz == 153000000, "v27 requires 153 MHz")
    infos = ([row for row in firmware_manifest['results'] if row['workload'] == args.workload]
             if is_embench else [row for row in firmware_manifest["firmware"] if row["configuration"] == args.configuration])
    require(len(infos) == 1, "Firmware identity is ambiguous")
    firmware = (firmware_run / 'workloads' / args.workload / 'firmware.hex' if is_embench
                else firmware_run / "firmware" / args.configuration / "firmware.hex")
    require(helper.sha(firmware) == infos[0]["firmware_sha256"], "Firmware bytes changed")
    if not os.environ.get("PANGO_LICENSE_FILE"):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            os.environ["PANGO_LICENSE_FILE"] = winreg.QueryValueEx(key, "PANGO_LICENSE_FILE")[0]
    require(bool(os.environ.get("PANGO_LICENSE_FILE")), "PDS license configuration missing")
    variants_root = Path('D:\\AAAFPGA\\ZGTC_RISC_CPU\\cpu_paper\\variants\\accepted-153-valid-ram-v31-r1')
    variants = json.loads(text(variants_root / "manifest.json"))
    import psutil
    require(not any(p.info['name'] and p.info['name'].lower() in ('pds_shell.exe','cdt_ins.exe') for p in psutil.process_iter(['name'])), 'Another native PDS job is active')
    run = ROOT / "results" / ("physical-" + ('redirect-' + args.variant + '-' + args.workload + '-packing3_compact0') + "-s" + str(args.seed) + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    record = {"schema": 1, "status": "running", "protocol": "v27", "firmware_protocol": firmware_manifest["protocol"], "implementation_profile": 'packing3_compact0', "implementation_options": ['-logic_optimize_enable', 'TRUE', '-logic_optimize_lut6d_combing_strategy', '3', '-plc_decongestion', '0'], "variant": args.variant, "placement_seed": args.seed,
              "device": "PG2L200H-6FBB676", "implementation_tool": "Windows PDS 2022.2-SP6.4 ADS",
              "configured_clock_hz": clock_hz, "measured_clock_hz": None, "hardware_validated": False,
              "firmware": infos[0], "firmware_manifest_sha256": helper.sha(firmware_run / "manifest.json"),
              "variant_manifest_sha256": helper.sha(variants_root / "manifest.json"),
              "hardware_parameters": helper.PARAMS, "uart_profile": "RemoteLab", "uart_baud": 115200,
              "ila": {"data_channels":42,"trigger_channels":33,"depth":1024,"clock":"cpu_clk"}}
    if is_embench:
        record.update(workload=args.workload, purpose='v27 redirect optimization with shared loader and full historical ILA',
                      source_reference=str(variants_root / args.variant))
    def save():
        helper.write_json(run / "manifest.json", record)
    save(); print("RUN " + str(run), flush=True)
    try:
        source = run / "inputs"
        for category, glob in (("rtl","*.sv"),("fpga","*.sv"),("constraints","*.fdc")):
            for original in ((variants_root / args.variant) / category).glob(glob):
                relative = category + "/" + original.name
                require(helper.sha(original) == variants["variants"][args.variant]["hashes"][relative], "Variant bytes changed: " + relative)
                helper.snapshot(original, source / relative)
        templates = {"pds_soc_top.v.in": REFERENCE / "scripts/pds_soc_top.v.in",
                     "pds_report.py": REFERENCE / "scripts/pds_report.py",
                     "audit_fetch_ila.py": REFERENCE / "audit_fetch_ila.py",
                     "audit_ila_mapping.py": REFERENCE.parent / "full_redirect_prime/audit_ila_mapping.py",
                     "ila_pipeline_minimal_config.py": ROOT.parent / "cpu/scripts/ila_pipeline_minimal_config.py",
                     "template.fic": ROOT.parent / "cpu/scripts/cpu_ila_regfilefanout157500_minimal.fic.in",
                     "runner.py": Path(__file__), "run_embench.py": Path(helper.__file__),
                     "audit_physical_timing.py": ROOT / "scripts/audit_physical_timing.py",
                     "redirect_fetch_alias.py": ROOT / "scripts/redirect_fetch_alias.py",
                     "redirect_implementation_profiles.py": ROOT / "scripts/redirect_implementation_profiles.py"}
        for name, original in templates.items():
            helper.snapshot(original, source / "tools" / name)
        for name in ("protocol_v1.md", "protocol_v2.md", "protocol_v3.md", "protocol_v4.md"):
            helper.snapshot(ROOT / name, source / name)
        if firmware_manifest["protocol"]=="v6":
            helper.snapshot(ROOT / "protocol_v6.md",source / "protocol_v6.md")
        if is_embench:
            helper.snapshot(ROOT / 'protocol_v25.md', source / 'protocol_v25.md')
            if firmware_manifest['protocol'] == 'v26': helper.snapshot(ROOT / 'protocol_v26.md', source / 'protocol_v26.md')
            helper.snapshot(firmware_run / 'manifest.json', source / 'firmware-manifest.json')
            helper.snapshot(firmware_run / 'source-hashes.json', source / 'firmware-source-hashes.json')
        helper.snapshot(ROOT / "protocol_v27.md", source / "protocol_v27.md")
        helper.snapshot(ROOT / "protocol_v27_implementation_profiles_v1.md", source / "protocol_v27_implementation_profiles_v1.md")
        helper.snapshot(ROOT / "protocol_v27_implementation_profiles_v2.md", source / "protocol_v27_implementation_profiles_v2.md")
        helper.snapshot(ROOT / "scripts/selected_clock_profiles.py", source / "tools/selected_clock_profiles.py")
        helper.snapshot(ROOT / "plans/v31_vex_stages_and_153_resource_efficiency.md", source / "v31-plan.md")
        helper.snapshot(variants_root / "manifest.json", source / "variant-manifest.json")
        helper.snapshot(firmware, source / "firmware.hex")
        top = text(source / "tools/pds_soc_top.v.in")
        params = dict(helper.PARAMS)
        params.pop("MEMORY_ADDRESS_BITS")
        params["PREDICTOR"] = params.pop("ENABLE_PREDICTOR")
        params.update(CLOCK_HZ=clock_hz, UART_BAUD=115200, FIRMWARE_HEX=(source / "firmware.hex").as_posix())
        for key,value in params.items():
            token = "__"+key+"__"
            require(token in top, "Missing wrapper parameter: " + key)
            top = top.replace(token,str(value))
        require(not re.search(r"__[A-Z_]+__",top), "Unresolved wrapper parameter")
        (source / "pds_soc_top.v").write_text(top,encoding="utf-8")
        hashes = {p.relative_to(source).as_posix(): helper.sha(p) for p in source.rglob("*") if p.is_file()}
        helper.write_json(run / "source-hashes.json", hashes)
        synthesis = run / "synthesis"; synthesis.mkdir()
        lines = ["add_design " + tcl_path(p) for p in sorted((source / "rtl").glob("*.sv"))]
        lines += ["add_design " + tcl_path(source / "pds_soc_top.v"), "add_design " + tcl_path(source / "fpga/rv32_pll.sv")]
        lines += ["add_constraint " + tcl_path(source / "constraints" / name) for name in ("board.fdc","uart_remotelab.fdc")]
        lines += ["set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676",
                  "compile -system_verilog -top_module pds_soc_top", "synthesize -ads -selected_syn_tool_opt 2"]
        write_lines(synthesis / "build.tcl", lines)
        invoke(PDS / "pds_shell.exe", ["-file",(synthesis / "build.tcl").as_posix(),"-work_dir",synthesis.as_posix(),"-project_name","cpu_ablation"], synthesis,"pds",1800)
        require("Executing : synthesize -ads -selected_syn_tool_opt 2 successfully." in text(synthesis / "run.log"), "ADS synthesis completion not proven")
        record["stage"] = "synthesized"; save()
        stage = run / "implementation"; stage.mkdir()
        for name, original in {"source.adf": synthesis / "synthesize/pds_soc_top_syn.adf", "netlist.v": synthesis / "synthesize/pds_soc_top_syn.vm"}.items():
            helper.snapshot(original, stage / name)
        write_lines(stage / "probe.tcl", ["ins_new " + tcl_path(stage / "probe.fic"), "ins_set_file -input " + tcl_path(stage / "source.adf"), "ins_list_nets", "exit"])
        native_args = ["-device","PG2L200H","-package","FBB676","-speedgrade","-6","-file"]
        probe = invoke(PDS / "cdt_ins.exe", native_args+[(stage / "probe.tcl").as_posix()],stage,"probe",300)
        available = re.findall(r"^\d+\s*:\s*(\S+)\s+\S+\s*$",probe,re.M)
        fic = text(source / "tools/template.fic").replace("__SOURCE_ADF__",(stage / "source.adf").as_posix())
        for index in range(5):
            candidates = [f"board/soc/core/pipeline_valid[{index}]" if index < 4 else "board/soc/core/board/unused_trace_valid",f"board/soc/unused_pipeline_valid[{index}]"]
            selected = [name for name in candidates if available.count(name) == 1]
            require(len(selected) == 1,"Missing or ambiguous pipeline channel: " + str(index))
            pattern = rf"(?m)^Project\.unit<0>\.dataChannel<{32+index}>=[^\r\n]*"
            require(len(re.findall(pattern,fic)) == 1,"Missing FIC data channel")
            fic = re.sub(pattern, f"Project.unit<0>.dataChannel<{32+index}>="+selected[0],fic)
        fetch_alias = load_module(source / "tools/redirect_fetch_alias.py", "frozen_fetch_alias")
        fic, fetch_proof = fetch_alias.prepare(text(stage / "netlist.v"), probe, fic)
        helper.write_json(stage / "fetch-alias-proof.json", fetch_proof)
        (stage / "cpu-remapped.fic").write_text(fic,encoding="utf-8")
        write_lines(stage / "verify.tcl",["ins_open " + tcl_path(stage / "cpu-remapped.fic"),"ins_core_info -core 0","ins_core_info -core 0 -trig 0","ins_save","exit"])
        verified = invoke(PDS / "cdt_ins.exe",native_args+[(stage / "verify.tcl").as_posix()],stage,"verify",300)
        require(not text(stage / "probe.stderr.log").strip() and not text(stage / "verify.stderr.log").strip(),"Native inserter stderr is nonempty")
        namespace = {"re":re,"require":require}
        normalizer = original_function(source / "tools/audit_ila_mapping.py","normalize_pipeline_mapping",namespace)
        namespace["shared"] = SimpleNamespace(normalize_pipeline_mapping=normalizer)
        mapping = original_function(source / "tools/audit_fetch_ila.py","normalize_mapping",namespace)
        canonical_fic,canonical_output,aliases = mapping(text(stage / "netlist.v"),text(stage / "cpu-remapped.fic"),verified,probe)
        canonical_fic, canonical_output, fetch_aliases = fetch_alias.normalize(
            text(stage / "netlist.v"), probe, canonical_fic, canonical_output, fetch_proof)
        aliases.update(fetch_aliases)
        validated = load_module(source / "tools/ila_pipeline_minimal_config.py","frozen_ila_validator").validate_config(canonical_fic,canonical_output)
        validated["aliases"] = aliases
        helper.write_json(stage / "mapping-audit.json",validated)
        record["stage"] = "ila_mapping_verified"; save()
        write_lines(stage / "build.tcl", ["add_design " + tcl_path(stage / "netlist.v")]
                    + ["add_constraint " + tcl_path(source / "constraints" / name) for name in ("board.fdc","uart_remotelab.fdc")]
                    + ["add_fic " + tcl_path(stage / "cpu-remapped.fic"),"set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676",
                       "compile -system_verilog -top_module pds_soc_top","dev_map -input_db_file " + tcl_path(stage / "source.adf"),
                       "pnr -gplace_seed " + str(args.seed) + ' -logic_optimize_enable TRUE -logic_optimize_lut6d_combing_strategy 3 -plc_decongestion 0',"report_timing","gen_bit_stream"])
        implementation_inputs = {name: helper.sha(stage / name) for name in ("source.adf","netlist.v","cpu-remapped.fic","build.tcl","mapping-audit.json","fetch-alias-proof.json")}
        helper.write_json(stage / "input-hashes.json",implementation_inputs)
        invoke(PDS / "pds_shell.exe",["-file",(stage / "build.tcl").as_posix(),"-work_dir",stage.as_posix(),"-project_name","cpu_ila"],stage,"pds",7200)
        timing, log = stage / "report_timing/pds_soc_top.rtr", stage / "run.log"
        report = load_module(source / "tools/pds_report.py","frozen_pds_parser").parse_ila_reports(text(timing),text(log),clock_hz)
        helper.write_json(stage / "resource-timing-summary.json",report)
        timing_audit = load_module(source / "tools/audit_physical_timing.py","frozen_multicorner_audit").audit(run)
        helper.write_json(stage / "multicorner-audit.json",timing_audit)
        bitstream = stage / "generate_bitstream/pds_soc_top.sbit"
        require(bitstream.is_file(),"Expected bitstream missing")
        for name,digest in implementation_inputs.items():
            require(helper.sha(stage / name) == digest,"Implementation input changed: " + name)
        for name,digest in hashes.items():
            require(helper.sha(source / name) == digest,"Snapshot changed: " + name)
        record.update(status="internal_timing_passed" if report["constraints_met"] and timing_audit["internal_multicorner_timing_passed"] else "timing_failed",
                      stage="implemented", report=report, timing_audit=timing_audit, bitstream_sha256=helper.sha(bitstream),
                      output_hashes={str(p.relative_to(run)):helper.sha(p) for p in (timing,log,bitstream)})
    except Exception as error:
        record.update(status="integration_failed",error=str(error)); raise
    finally:
        save()
    print("COMPLETE " + str(run),flush=True)


if __name__ == "__main__":
    main()
