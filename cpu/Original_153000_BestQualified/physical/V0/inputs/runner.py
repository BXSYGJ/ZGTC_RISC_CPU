"""Implement a frozen RV32IMC snapshot with the accepted Windows PDS settings."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4
import winreg

import psutil
import run_embench as helper
from run_physical_ila import PDS, invoke, load_module, require, tcl_path, write_lines
from selected_clock_profiles import PROFILES as BASE_PROFILES

ROOT = helper.ROOT
VARIANT = ROOT / "variants/rvc-153-valid-ram-v1/rv32imc_153"
REFERENCE = ROOT / "results/physical-redirect-accepted_valid_ram-uart-loader-packing3_compact0-s3-20260924T152714Z-902781d3"
PROFILES = dict(BASE_PROFILES)
PROFILES["packing3_compact0_refine40"] = BASE_PROFILES["packing3_compact0"] + BASE_PROFILES["refine40"]
PROFILES["packing3_compact0_module_planning"] = BASE_PROFILES["packing3_compact0"] + BASE_PROFILES["module_planning"]
PROFILES["packing3_compact0_routing99"] = BASE_PROFILES["packing3_compact0"] + BASE_PROFILES["routing99"]
PROFILES["packing3_compact0_route_iterate3"] = BASE_PROFILES["packing3_compact0"] + BASE_PROFILES["route_iterate3"]
PROFILES["packing3_nodup_refine40"] = BASE_PROFILES["packing3_nodup"] + BASE_PROFILES["refine40"]
PROFILES["packing3_nodup_compact0"] = BASE_PROFILES["packing3_nodup"] + BASE_PROFILES["compact0"]
PROFILES["packing3_nodup_route_iterate3"] = BASE_PROFILES["packing3_nodup"] + BASE_PROFILES["route_iterate3"]
PROFILES["packing3_nodup_refine40_route_iterate3"] = PROFILES["packing3_nodup_refine40"] + BASE_PROFILES["route_iterate3"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--variant", type=Path, default=VARIANT)
    parser.add_argument("--clock-hz", type=int, choices=(145125000, 153000000), default=153000000)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="packing3_compact0")
    parser.add_argument("--seed", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--uart-baud", type=int, choices=(9600, 115200), default=115200)
    parser.add_argument("--history-bits", type=int, choices=(1, 2, 3, 4, 5))
    parser.add_argument("--counter-bits", type=int, choices=(1, 2))
    args = parser.parse_args()
    require(os.name == "nt", "Use Windows PDS")
    variant = args.variant.resolve()
    require(variant.is_relative_to((ROOT / "variants").resolve()), "Variant must be a project snapshot")
    require((variant / "rtl/rv32_rvc_frontend.sv").is_file(), "Missing RVC frontend")
    firmware = args.firmware.resolve()
    require(firmware.is_file() and firmware.is_relative_to(ROOT), "Firmware must be a project artifact")
    if not os.environ.get("PANGO_LICENSE_FILE"):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            os.environ["PANGO_LICENSE_FILE"] = winreg.QueryValueEx(key, "PANGO_LICENSE_FILE")[0]
    require(not any(process.info["name"] and process.info["name"].lower() in ("pds_shell.exe", "cdt_ins.exe") for process in psutil.process_iter(["name"])), "Another PDS job is active")
    run = ROOT / "results" / ("rvc-physical-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir()
    source = run / "inputs"
    record = dict(status="running", configured_clock_hz=args.clock_hz, hardware_validated=False,
                  instrumentation_profile="none", implementation_profile=args.profile,
                  placement_seed=args.seed, history_bits_override=args.history_bits, counter_bits_override=args.counter_bits,
                  uart_baud=args.uart_baud,
                  device="PG2L200H-6FBB676", source=str(variant), firmware_sha256=helper.sha(firmware))
    helper.write_json(run / "manifest.json", record)
    print("RUN " + str(run), flush=True)
    try:
        for category, pattern in (("rtl", "*.sv"), ("fpga", "*.sv"), ("constraints", "*.fdc")):
            for original in (variant / category).glob(pattern):
                helper.snapshot(original, source / category / original.name)
        helper.snapshot(firmware, source / "firmware.hex")
        for parameter, value in (("HISTORY_BITS", args.history_bits), ("COUNTER_BITS", args.counter_bits)):
            if value is None:
                continue
            btb = source / "rtl/rv32_btb.sv"
            modified, count = re.subn(r"parameter integer " + parameter + r"=\d+,", f"parameter integer {parameter}={value},", btb.read_text(encoding="utf-8-sig"))
            require(count == 1, "Expected one BTB parameter declaration")
            btb.write_text(modified, encoding="utf-8")
        helper.snapshot(__file__, source / "runner.py")
        top = (variant / "fpga/pds_soc_top.v").read_text(encoding="utf-8-sig")
        clocks = re.findall(r"\.CLOCK_HZ\((\d+)\)", top)
        require(clocks == [str(args.clock_hz)] * 2, "Wrapper clock differs from requested clock")
        top, count = re.subn(r'\.INIT_FILE\("[^"]+"\)', '.INIT_FILE("' + (source / "firmware.hex").as_posix() + '")', top)
        require(count == 1, "Expected one firmware binding")
        top, count = re.subn(r"\.UART_BAUD\(\d+\)", f".UART_BAUD({args.uart_baud})", top)
        require(count == 1, "Expected one UART baud binding")
        (source / "pds_soc_top.v").write_text(top, encoding="utf-8")
        hashes = {path.relative_to(source).as_posix(): helper.sha(path) for path in source.rglob("*") if path.is_file()}
        helper.write_json(run / "source-hashes.json", hashes)
        synthesis = run / "synthesis"
        synthesis.mkdir()
        constraints = ["add_constraint " + tcl_path(source / "constraints" / name) for name in ("board.fdc", "uart_remotelab.fdc")]
        architecture = "set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676"
        lines = ["add_design " + tcl_path(path) for path in sorted((source / "rtl").glob("*.sv"))]
        lines += ["add_design " + tcl_path(source / name) for name in ("pds_soc_top.v", "fpga/rv32_pll.sv")]
        write_lines(synthesis / "build.tcl", lines + constraints + [architecture, "compile -system_verilog -top_module pds_soc_top", "synthesize -ads -selected_syn_tool_opt 2"])
        invoke(PDS / "pds_shell.exe", ["-file", str(synthesis / "build.tcl"), "-work_dir", str(synthesis), "-project_name", "rvc153"], synthesis, "pds", 1800)
        require("Executing : synthesize -ads -selected_syn_tool_opt 2 successfully." in (synthesis / "run.log").read_text(encoding="utf-8-sig"), "Synthesis did not complete")
        stage = run / "implementation"
        stage.mkdir()
        for target, original in (("source.adf", "pds_soc_top_syn.adf"), ("netlist.v", "pds_soc_top_syn.vm")):
            helper.snapshot(synthesis / "synthesize" / original, stage / target)
        write_lines(stage / "build.tcl", ["add_design " + tcl_path(stage / "netlist.v")] + constraints + [architecture,
            "compile -system_verilog -top_module pds_soc_top", "dev_map -input_db_file " + tcl_path(stage / "source.adf"),
            "pnr -gplace_seed " + str(args.seed) + " " + " ".join(PROFILES[args.profile]), "report_timing", "gen_bit_stream"])
        record["stage"] = "synthesized"
        helper.write_json(run / "manifest.json", record)
        invoke(PDS / "pds_shell.exe", ["-file", str(stage / "build.tcl"), "-work_dir", str(stage), "-project_name", "rvc153"], stage, "pds", 7200)
        report_parser = load_module(REFERENCE / "inputs/tools/pds_report.py", "rvc_report_parser")
        timing_text = (stage / "report_timing/pds_soc_top.rtr").read_text(encoding="utf-8-sig")
        report = report_parser.parse_ila_reports(timing_text, (stage / "run.log").read_text(encoding="utf-8-sig"), args.clock_hz)
        setup_uncertainties = re.findall(
            r"clock uncertainty\s+(-?\d+\.\d+)\s+-?\d+\.\d+\s*\n\s*Setup time", timing_text)
        require(len(setup_uncertainties) >= 2 and
                all(abs(float(value) + 0.150) < 0.0001 for value in setup_uncertainties),
                "Final setup timing must retain 0.150 ns uncertainty")
        record["setup_uncertainty_ns"] = 0.150
        record["setup_uncertainty_paths_checked"] = len(setup_uncertainties)
        from audit_physical_timing import audit
        timing = audit(run)
        helper.write_json(stage / "resource-timing-summary.json", report)
        helper.write_json(stage / "multicorner-audit.json", timing)
        for name, digest in hashes.items():
            require(helper.sha(source / name) == digest, "Physical source snapshot changed")
        record.update(status="internal_timing_passed" if report["constraints_met"] and timing["internal_multicorner_timing_passed"] else "timing_failed", report=report, timing_audit=timing,
                      bitstream_sha256=helper.sha(stage / "generate_bitstream/pds_soc_top.sbit"))
    except Exception as error:
        record.update(status="failed", error=str(error))
        raise
    finally:
        helper.write_json(run / "manifest.json", record)
    print("COMPLETE " + str(run), flush=True)


if __name__ == "__main__":
    main()
