import json
import re
from datetime import datetime
from pathlib import Path

from audit_ila_mapping import ROOT, STAGE, audit, digest, require
from pds_report import parse_ila_reports


def qualify(stage=STAGE, audit_mapping=True):
    invocation = json.loads((stage / "invocation.json").read_text(encoding="utf-8-sig"))
    require(invocation["ExitCode"] == 0, "PDS did not finish successfully")
    require(Path(invocation["WorkingDirectory"]).resolve() == stage.resolve(), "Wrong run directory")
    require(invocation["PlacementSeed"] == 2, "Wrong placement seed")
    started = datetime.fromisoformat(invocation["StartedUtc"]).timestamp()
    finished = datetime.fromisoformat(invocation["FinishedUtc"]).timestamp()
    require(finished >= started, "Invalid invocation interval")
    required_inputs = {"source.adf", "netlist.v", "firmware.hex", "cpu-remapped.fic", "board.fdc", "uart_remotelab.fdc", "build.tcl", "mapping-audit.json"}
    require(set(invocation["Inputs"]) == required_inputs, "Incomplete implementation input hashes")
    for name, expected in invocation["Inputs"].items():
        require(digest(stage / name) == expected, "Implementation input changed: " + name)
    if audit_mapping:
        require(stage.resolve() == STAGE.resolve(), "Unexpected audited stage")
        audit()
    mapping = json.loads((stage / "mapping-audit.json").read_text(encoding="utf-8"))
    require((mapping["data_channels"], mapping["trigger_channels"], mapping["depth"], mapping["clock"]) == (42, 33, 1024, "cpu_clk"), "Wrong ILA dimensions or clock")
    outputs = {
        "timing": "report_timing/pds_soc_top.rtr",
        "log": "run.log",
        "bitstream": "generate_bitstream/pds_soc_top.sbit",
        "stdout": "pds.stdout.log",
        "stderr": "pds.stderr.log",
    }
    for name, relative in outputs.items():
        filename = stage / relative
        require(filename.is_file(), "Missing generated output: " + name)
        require(started - 2 <= filename.stat().st_mtime <= finished + 2, "Output not from invocation interval: " + name)
        if name != "stderr":
            require(filename.stat().st_size > 0, "Empty generated output: " + name)
    log = (stage / outputs["log"]).read_text(encoding="utf-8-sig")
    stderr = (stage / outputs["stderr"]).read_text(encoding="utf-8-sig")
    stdout = (stage / outputs["stdout"]).read_text(encoding="utf-8-sig")
    require(not re.search(r"^\s*(?:E:|Error:)", log + stderr + stdout, re.M), "PDS reported an error")
    commands = [line.strip() for line in (stage / "build.tcl").read_text(encoding="utf-8-sig").splitlines() if line.startswith("pnr")]
    require(commands == ["pnr -gplace_seed 2"], "Unexpected placement command")
    report = parse_ila_reports((stage / outputs["timing"]).read_text(encoding="utf-8-sig"), log, 157500000)
    report.update({
        "schema": 1,
        "run_directory": str(stage),
        "placement_seed": 2,
        "baseline_post_route_luts": 9374,
        "lut_change_vs_baseline": report["resources"]["post_route_luts"] - 9374,
        "physical_timing_passed": report["constraints_met"],
        "resource_efficiency_qualified": False,
        "hardware_validated": False,
        "full_score_qualified": False,
        "coremark_score": None,
        "ila": {name: mapping[name] for name in ("data_channels", "trigger_channels", "depth", "clock")},
        "inputs_sha256": invocation["Inputs"],
        "outputs_sha256": {name: digest(stage / relative) for name, relative in outputs.items()},
    })
    return report


if __name__ == "__main__":
    result = qualify()
    (STAGE / "physical-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["physical_timing_passed"] else 2)

