import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "build/full-resource-opt-timer-keep-stage"
sys.path.insert(0, str(ROOT / "scripts"))
from ila_pipeline_minimal_config import validate_config
from pds_report import parse_ila_reports


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_binding(source):
    accepted = ROOT / "build/regfile-valid-fanout-stage/build/pds/20260909-124605-a402f7e8"
    reference = json.loads((accepted / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    snapshot = json.loads((source / "source-snapshot.json").read_text(encoding="utf-8-sig"))
    expected = dict(reference["Files"])
    expected["rtl/rv32_peripherals.sv"] = digest(Path(__file__).parent / "rv32_peripherals.sv")
    require(len(expected) == 20 and snapshot["Files"] == expected, "Incomplete or changed full-function source set")
    for relative, expected_hash in expected.items():
        require(digest(source / "source" / relative) == expected_hash, "Physical input changed: " + relative)
    original = (accepted / "source/rtl/rv32_peripherals.sv").read_text(encoding="utf-8-sig")
    candidate = (source / "source/rtl/rv32_peripherals.sv").read_text(encoding="utf-8-sig")
    require(original.count("(* syn_keep=1 *) ") == 4 and candidate == original.replace("(* syn_keep=1 *) ", ""), "Peripheral behavior changed")
    def normalize(path):
        text = path.read_text(encoding="utf-8-sig")
        result, count = re.subn(r'\.INIT_FILE\("[^"\n]+"\)', '.INIT_FILE("<firmware>")', text)
        require(count == 1, "Missing or ambiguous firmware initializer")
        return result
    require(normalize(source / "pds_soc_top.v") == normalize(accepted / "pds_soc_top.v"), "Physical parameters or GPIO/UART wiring changed")
    require(digest(source / "firmware.hex") == "0E5EAD297589F9689CE8D9D60163DD7DD87FD71FF7EC11731545DE9CD9E99ABF", "Wrong performance firmware")
    return {"source": source.as_posix(), "source_files": expected,
            "artifacts": {name: digest(source / name) for name in ["source-snapshot.json", "pds_soc_top.v", "firmware.hex", "synthesize/pds_soc_top_syn.adf", "synthesize/pds_soc_top_syn.vm"]}}


def audit(source, build, mode):
    binding = source_binding(source)
    binding_path = build / "source-binding.json"
    if mode == "prepare":
        require(not binding_path.exists(), "Do not overwrite an existing insertion binding")
        binding_path.write_text(json.dumps(binding, indent=2) + "\n", encoding="utf-8")
        return binding
    require(binding == json.loads(binding_path.read_text(encoding="utf-8-sig")), "Source changed after insertion started")
    copies = {"source.adf":"synthesize/pds_soc_top_syn.adf", "netlist.v":"synthesize/pds_soc_top_syn.vm", "firmware.hex":"firmware.hex"}
    for local, original in copies.items():
        require(digest(build / local) == binding["artifacts"][original], "Inserted source copy changed: " + local)
    for name in ["board.fdc", "uart_remotelab.fdc"]:
        require(digest(build / name) == binding["source_files"]["constraints/" + name], "Constraint copy changed")
    config = validate_config((build / "cpu.fic").read_text(encoding="utf-8-sig"),
                             (build / "verify.stdout.txt").read_text(encoding="utf-8-sig"))
    require(not re.search(r"(?im)^\s*(E:|Error:)", (build / "verify.stderr.txt").read_text(encoding="utf-8-sig")), "Inserter error")
    result = {"scope":"complete_peripherals_and_42_data_33_trigger_ila_local_candidate", "source_binding_sha256":digest(binding_path),
              "ila":config, "full_score_qualified":False, "hardware_validated":False}
    if mode == "result":
        summary = parse_ila_reports((build / "report_timing/pds_soc_top.rtr").read_text(encoding="utf-8-sig"),
                                (build / "run.log").read_text(encoding="utf-8-sig"), 157500000)
        result["physical"] = summary
        result["resource_improvement_at_fixed_execution_pending_full_run"] = bool(summary["constraints_met"] and summary["resources"]["post_route_luts"] < 9374)
        result["rejection_reasons"] = []
        if not summary["constraints_met"]:
            result["rejection_reasons"].append("157.5 MHz inserted timing failed")
        if summary["resources"]["post_route_luts"] >= 9374:
            result["rejection_reasons"].append("Total inserted LUT count did not improve")
        result["candidate_rejected"] = bool(result["rejection_reasons"])
        if summary["constraints_met"]:
            require((build / "generate_bitstream/pds_soc_top.sbit").is_file(), "Missing inserted bitstream")
        files = ["cpu.fic", "verify.stdout.txt", "verify.stderr.txt", "build.tcl", "placement.json", "report_timing/pds_soc_top.rtr", "run.log"]
        if (build / "generate_bitstream/pds_soc_top.sbit").is_file():
            files.append("generate_bitstream/pds_soc_top.sbit")
        result["artifacts"] = {name:digest(build / name) for name in files}
    (build / (mode + "-qualification.json")).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("build", type=Path)
    parser.add_argument("--mode", choices=["prepare", "mapping", "result"], required=True)
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.source, arguments.build, arguments.mode),indent=2))
