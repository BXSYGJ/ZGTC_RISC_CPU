import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
sys.path.insert(0, str(BASE.parents[1] / "scripts"))
sys.path.insert(0, str(BASE / "scripts"))
from load_use_profile import file_hash, load_json, require
from run_load_use_profile import verified_build
from run_coremark_compiled import validate_compiler_warnings, check_simulation_result

SOURCES = ("20260910-233631-e15b5716", "20260910-233649-cc01ef34")


def run(command, log):
    completed = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=300)
    text = completed.stdout + completed.stderr
    log.write_text(text, encoding="utf-8")
    require(completed.returncode == 0, "Correlated return-stack command failed: " + str(log))
    return text


def main(validation, attempt=""):
    require(not attempt or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", attempt), "Invalid screen attempt label")
    original = BASE / "build/compiled" / SOURCES[int(validation)]
    manifest, reference = verified_build(original)
    require(reference["validation_run"] is validation and reference["iterations"] == 10, "Wrong reference seed or iteration count")
    for relative, expected in manifest["SourceSnapshot"].items():
        require(file_hash(BASE / relative) == expected, "Base source changed: " + relative)
    output = ROOT / "build" / (("v1" if validation else "v0") + ("-" + attempt if attempt else ""))
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(original / "source", output / "source")
    for filename in ("rv32_core.sv", "rv32_btb.sv"):
        shutil.copyfile(ROOT / filename, output / "source/rtl" / filename)
    shutil.copyfile(original / "firmware.hex", output / "firmware.hex")
    shutil.copyfile(Path(__file__), output / "runner-original.py")
    sources = {relative: file_hash(output / "source" / relative) for relative in manifest["SourceSnapshot"]}
    changes = [relative for relative, expected in sources.items() if expected != manifest["SourceSnapshot"][relative]]
    require(set(changes) == {"rtl/rv32_core.sv", "rtl/rv32_btb.sv"}, "Screen must change only return-stack core and predictor RTL")
    command = [argument.replace(str(original), str(output)) for argument in manifest["CompileCommand"]]
    record = {"schema": 1, "scope": "matched short RTL relation-reuse screen; not timing, resource or hardware qualification",
              "validation_run": validation, "base_build": str(original), "base_manifest_sha256": file_hash(original / "manifest.json"),
              "firmware_sha256": file_hash(output / "firmware.hex"), "source_hashes": sources,
              "compile_command": command, "runner_sha256": file_hash(Path(__file__)), "passed": False,
              "hardware_parameters": manifest["HardwareParameters"], "firmware_build": manifest["FirmwareBuild"]}
    (output / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    text = run(command, output / "compile.log")
    validate_compiler_warnings(text, output / "source")
    run([output / "objects/Vrv32_soc", output / "uart.log", "10000000"], output / "execute.log")
    measured = check_simulation_result((output / "uart.log").read_text(), manifest["FirmwareBuild"], manifest["HardwareParameters"], True)
    for key in ("validation_run", "iterations", "retired", "seed_crc", "final_crc", "clock_hz"):
        require(measured[key] == reference[key], "Architectural or firmware result changed: " + key)
    for relative, expected in sources.items():
        require(file_hash(output / "source" / relative) == expected, "Captured screen source changed")
        current = ROOT / Path(relative).name if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv") else BASE / relative
        require(file_hash(current) == expected, "Current screen source changed")
    require(file_hash(output / "firmware.hex") == record["firmware_sha256"] == manifest["FirmwareSha256"], "Screen firmware changed")
    parent_run = ROOT.parent / "full_id_relation_mask1/build" / ("v1" if validation else "v0")
    parent_manifest = load_json(parent_run / "manifest.json")
    require(parent_manifest["passed"] is True, "Immediate parent short run incomplete")
    for relative, checksum in parent_manifest["outputs"].items():
        require(file_hash(parent_run / relative) == checksum, "Parent short output changed")
    require(parent_manifest["firmware_sha256"] == record["firmware_sha256"], "Parent short firmware differs")
    require((output / "uart.log").read_bytes() == (parent_run / "uart.log").read_bytes(), "Relation reuse changes short UART or execution cycles")
    record["parent_manifest_sha256"] = file_hash(parent_run / "manifest.json")
    record["parent_short_uart_identical"] = True
    comparison = {"validation_run": validation, "reference_cycles": reference["cycles"], "cycles": measured["cycles"],
                  "cycles_saved": reference["cycles"] - measured["cycles"], "execution_efficiency_ratio": reference["cycles"] / measured["cycles"],
                  "result": measured, "physical_timing_qualified": False, "resource_efficiency_qualified": False, "hardware_validated": False}
    (output / "result.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    record.update(passed=True, outputs={name: file_hash(output / name) for name in ("objects/Vrv32_soc", "uart.log", "result.json", "compile.log", "execute.log")})
    (output / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--attempt", default="")
    arguments = parser.parse_args()
    main(arguments.validation, arguments.attempt)
