import json
import re
from fractions import Fraction
from pathlib import Path

import audit_full_ila as performance_image
import audit_validation_ila as validation_image
import run_long as runner
from audit_joint import validate_simulation_metadata

ROOT = Path(__file__).resolve().parent
BASE = runner.BASE
SCORE_FLOOR = Fraction("501.0657302224314")
RESOURCE_FLOOR = Fraction("0.053452712846429634")
OUTPUTS = {"objects/Vrv32_soc", "uart.log", "result.json", "compile.log", "execute.log"}
STAGES = ("id-relation-mask1-seed1", "id-relation-mask1-v1-seed1")
load_json = runner.load_json
require = runner.require
digest = runner.file_hash


def portable(path):
    value = str(path).replace(chr(92), "/")
    if re.match(r"^[A-Za-z]:/", value):
        value = "/mnt/" + value[0].lower() + value[2:]
    return value.rstrip("/")


def read_physical(validation):
    module = validation_image if validation else performance_image
    stage = ROOT / "build/ila" / STAGES[int(validation)]
    original_hash = digest(stage / "physical-qualification.json")
    module.mapping(stage, module.SOURCE)
    actual = module.qualify(stage, audit_mapping=False, source=module.SOURCE,
                            validation=validation, placement_seed=1)
    actual["source_binding"] = module.binding(module.SOURCE)
    require(actual == load_json(stage / "physical-qualification.json"), "Stored physical qualification differs from current audit")
    require(actual["physical_timing_passed"] is True, "Full image fails timing")
    require(digest(stage / "physical-qualification.json") == original_hash, "Physical receipt changed during audit")
    return actual


def read_run(validation, physical, prerequisite):
    directory = ROOT / "build" / ("long-v1" if validation else "long-v0")
    original = BASE / "build/compiled" / runner.SOURCES[int(validation)]
    manifest = load_json(directory / "manifest.json")
    require(manifest["schema"] == 1 and manifest["passed"] is True, "Long run is incomplete")
    require(manifest["validation_run"] is validation, "Wrong long-run seed")
    require(manifest["simulation_clock_hz"] == 100000000 and manifest["uart_model_clock_hz"] == 3200,
            "Wrong simulation model clocks")
    require(manifest["max_cycles"] == 6000000000 and manifest["simulation_timeout_seconds"] == 7200,
            "Long execution bounds differ")
    require(manifest["physical_prerequisite"] == prerequisite, "Captured V0 physical prerequisite differs")
    require(portable(manifest["base_build"]) == portable(original), "Wrong reference directory")
    require(manifest["base_manifest_sha256"] == digest(original / "manifest.json"), "Reference manifest changed")
    reference_manifest, reference = runner.verified_build(original)
    bound = physical["source_binding"]
    validate_simulation_metadata(reference_manifest, bound, BASE)
    runner.validate_reference(reference_manifest, reference, validation, prerequisite)
    require(manifest["hardware_parameters"] == bound["hardware_parameters"] == reference_manifest["HardwareParameters"],
            "Simulation and physical hardware parameters differ")
    require(manifest["firmware_build"] == reference_manifest["FirmwareBuild"], "Long firmware manifest changed")
    require(manifest["firmware_sha256"] == bound["firmware_sha256"] == digest(directory / "firmware.hex")
            == reference_manifest["FirmwareSha256"] == manifest["firmware_build"]["HexSha256"],
            "Simulation firmware differs from its physical image")
    require(manifest["runner_sha256"] == digest(ROOT / "run_long.py") == digest(directory / "runner-original.py"),
            "Long runner changed")
    require(set(manifest["source_hashes"]) == set(reference_manifest["SourceSnapshot"]), "Incomplete long source inventory")
    changes = {name for name, checksum in manifest["source_hashes"].items()
               if checksum != reference_manifest["SourceSnapshot"][name]}
    require(changes == {"rtl/rv32_core.sv", "rtl/rv32_btb.sv"}, "Unexpected long source delta")
    for relative, checksum in manifest["source_hashes"].items():
        require(digest(directory / "source" / relative) == checksum, "Captured simulation source changed: " + relative)
        current = runner.source_path(relative) if relative.startswith("rtl/") else BASE / relative
        require(digest(current) == checksum, "Current simulation source changed: " + relative)
        require(digest(BASE / relative) == reference_manifest["SourceSnapshot"][relative], "Reference source changed: " + relative)
        if relative.startswith("rtl/"):
            require(bound["physical_source_hashes"].get(relative) == checksum, "Physical and simulated RTL differ: " + relative)
    expected_command = [argument.replace(portable(original), portable(directory))
                        for argument in reference_manifest["CompileCommand"]]
    require(manifest["compile_command"] == expected_command, "Long compiler command changed")
    require(set(manifest["outputs"]) == OUTPUTS, "Incomplete long output inventory")
    for relative, checksum in manifest["outputs"].items():
        require(digest(directory / relative) == checksum, "Long output changed: " + relative)
    compile_text = (directory / "compile.log").read_text(encoding="utf-8")
    warning_source = directory / "source/rtl/rv32_burst_ram.sv"
    compile_text = compile_text.replace(portable(warning_source), str(warning_source))
    runner.validate_compiler_warnings(compile_text, directory / "source")
    execute_text = (directory / "execute.log").read_text(encoding="utf-8")
    terminal = re.findall(r"^PASS compiled RTL simulation cycles=([0-9]+) retired=([0-9]+)$", execute_text, re.M)
    require(len(terminal) == 1 and 0 < int(terminal[0][0]) <= manifest["max_cycles"], "Missing or invalid simulator completion")
    uart = (directory / "uart.log").read_text(encoding="utf-8")
    result = runner.check_simulation_result(uart, manifest["firmware_build"], manifest["hardware_parameters"], False)
    require(result["iterations"] == 6000 and result["validation_run"] is validation, "Wrong measured seed or iteration count")
    require(result["clock_hz"] == physical["clock_hz"] and result["crc_valid"] is True
            and result["modeled_duration_at_least_10s"] is True, "Long measurement gate failed")
    for key in ("validation_run", "iterations", "retired", "seed_crc", "final_crc", "clock_hz"):
        require(result[key] == reference[key], "Long architectural result changed: " + key)
    expected = {"validation_run": validation, "reference_cycles": reference["cycles"], "cycles": result["cycles"],
                "cycles_saved": reference["cycles"] - result["cycles"],
                "execution_efficiency_ratio": reference["cycles"] / result["cycles"], "result": result,
                "physical_timing_qualified": False, "resource_efficiency_qualified": False, "hardware_validated": False}
    require(load_json(directory / "result.json") == expected, "Stored result differs from parsed UART")
    return {"validation_run": validation, "compiled_build": directory.name, "physical_build": STAGES[int(validation)],
            "result": result, "post_route_luts": physical["resources"]["post_route_luts"],
            "setup_wns_ns": physical["setup_wns_ns"], "bitstream_sha256": physical["outputs_sha256"]["bitstream"],
            "manifest_sha256": digest(directory / "manifest.json"),
            "physical_qualification_sha256": digest(ROOT / "build/ila" / STAGES[int(validation)] / "physical-qualification.json"),
            "binding": bound}


def evaluate(result, lut_count):
    require(type(lut_count) is int and lut_count > 0, "Invalid complete-system LUT count")
    for key in ("iterations", "cycles", "clock_hz"):
        require(type(result[key]) is int and result[key] > 0, "Invalid metric input: " + key)
    score = Fraction(result["iterations"] * result["clock_hz"], result["cycles"])
    execution = Fraction(result["iterations"] * 1000000, result["cycles"])
    resource = score / lut_count
    maximum_luts = score // RESOURCE_FLOOR
    return {"coremark_floor_passed": score >= SCORE_FLOOR, "resource_floor_passed": resource >= RESOURCE_FLOOR,
            "local_metric_gates_passed": score >= SCORE_FLOOR and resource >= RESOURCE_FLOOR,
            "modeled_iterations_per_second": float(score), "modeled_execution_efficiency": float(execution),
            "modeled_resource_efficiency": float(resource), "exact_score": str(score),
            "exact_execution_efficiency": str(execution), "exact_resource_efficiency": str(resource),
            "coremark_floor": str(SCORE_FLOOR), "resource_floor": str(RESOURCE_FLOOR),
            "maximum_luts_at_measured_score": maximum_luts,
            "minimum_lut_reduction_at_unchanged_score": max(0, lut_count - maximum_luts)}


def audit(write=False):
    baseline_path = ROOT.parents[1] / "build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json"
    baseline = load_json(baseline_path)
    require(baseline["coremark_pair_hardware_passed"] is True, "Accepted baseline is not hardware qualified")
    original = next(run["result"] for run in baseline["runs"] if run["result"]["validation_run"] is False)
    require(tuple(original[key] for key in ("iterations", "cycles", "clock_hz", "lut_count")) ==
            (6000, 1885980108, 157500000, 9374), "Unexpected accepted baseline")
    prerequisite = runner.physical_gate()
    runs = [read_run(validation, read_physical(validation), prerequisite) for validation in (False, True)]
    require(runs[0]["binding"]["physical_source_hashes"] == runs[1]["binding"]["physical_source_hashes"], "V0/V1 hardware sources differ")
    require(runs[0]["post_route_luts"] == runs[1]["post_route_luts"], "V0/V1 complete resource counts differ")
    metric = evaluate(runs[0]["result"], runs[0]["post_route_luts"])
    receipt = {"schema": 1, "scope": "source-bound paired long RTL and complete PDS images; not hardware scores",
               "local_pair_validated": True, **metric, "hardware_validated": False, "full_score_qualified": False,
               "baseline_replaced": False, "baseline_receipt_sha256": digest(baseline_path),
               "auditor_sha256": digest(Path(__file__)), "runs": runs}
    if write:
        destination = ROOT / "build/local-joint-score-resource-qualification.json"
        content = json.dumps(receipt, indent=2) + "\n"
        require(not destination.exists() or destination.read_text(encoding="utf-8") == content, "Refusing to overwrite changed joint receipt")
        destination.write_text(content, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    result = audit(write=True)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["local_metric_gates_passed"] else 2)
