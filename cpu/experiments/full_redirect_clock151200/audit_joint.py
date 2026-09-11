import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CPU = ROOT.parents[1]
sys.path.insert(0, str(CPU / "scripts"))
from frequency_promotion import Measurement
from frequency_target500 import compare_score_resource_tradeoff, coremark
from audit_binding import audit as audit_binding, digest, require
from qualify_full_ila import qualify
from run_coremark_compiled import check_simulation_result, verify_artifacts, hardware_parameters

RUNS = (
    (False, "20260911-001254-0e98e281", "20260910-233603-e3b63565", "20260910-redirect-clock151200-seed1"),
    (True, "20260911-001315-6a0c1e04", "20260911-001344-ee795aac", "20260911-redirect-clock151200-v1-seed1"),
)


def validate_simulation_metadata(manifest, binding, current_root):
    require(manifest.get("MeasurementKind") == "rtl_simulation_not_hardware", "Wrong simulation measurement label")
    require(manifest["ConfigurationInput"]["ClockHz"] == binding["clock_hz"], "Captured configuration clock differs")
    require(hardware_parameters(manifest["ConfigurationInput"]) == manifest["HardwareParameters"], "Captured configuration hardware differs")
    require(manifest["SimulationClockHz"] == 100000000 and manifest["UartModelClockHz"] == 3200, "Wrong simulation model clock")
    rtl = sorted(filename.relative_to(current_root).as_posix() for filename in (current_root / "rtl").glob("*.sv") if filename.name != "rv32_board_top.sv")
    compiled_inputs = rtl + ["sim/coremark_compiled.cpp"]
    expected_sources = set(compiled_inputs) | {"scripts/run_coremark_compiled.py", "scripts/check_coremark.py"}
    require(set(manifest["SourceSnapshot"]) == expected_sources, "Incomplete or unexpected simulation source set")
    build = manifest["BuildDirectory"].rstrip("/")
    expected_command = ["/usr/bin/verilator", "--cc", "--exe", "--build", "--Wall", "-Wno-fatal", "-j", "2",
                        "--top-module", "rv32_soc", "--Mdir", build + "/objects", "-CFLAGS", "-O3 -std=c++14",
                        "-GCLOCK_HZ=3200", "-GBAUD=100", '-GINIT_FILE="' + build + '/firmware.hex"']
    expected_command += [f"-G{name}={value}" for name, value in hardware_parameters(manifest["ConfigurationInput"]).items()]
    expected_command += [build + "/source/" + relative for relative in compiled_inputs]
    require(manifest["CompileCommand"] == expected_command, "Compile command differs from the captured configuration")


def read_run(directory, binding, validation, current_root=ROOT):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8-sig"))
    require(manifest["SimulationPassed"] and manifest.get("CompletedUtc"), "Long simulation not complete")
    validate_simulation_metadata(manifest, binding, current_root)
    verify_artifacts(directory, manifest)
    require(manifest["HardwareParameters"] == binding["hardware_parameters"], "Simulation hardware parameters differ")
    require(manifest["FirmwareSha256"] == binding["physical_firmware_sha256"] == manifest["FirmwareBuild"]["HexSha256"], "Simulation firmware differs from physical image")
    require(manifest["FirmwareBuild"]["ClockHz"] == binding["clock_hz"], "Simulation firmware clock differs")
    for relative, expected in manifest["SourceSnapshot"].items():
        require(digest(current_root / relative) == expected, "Current simulation source changed: " + relative)
        if relative.startswith("rtl/"):
            require(binding["physical_source_hashes"].get(relative) == expected, "Simulation RTL differs from physical source: " + relative)
    for filename, key in (("coremark.sim.uart", "UartSha256"), ("result.json", "ResultSha256")):
        require(digest(directory / filename) == manifest[key], "Simulation output changed: " + filename)
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    parsed = check_simulation_result((directory / "coremark.sim.uart").read_text(encoding="utf-8"),
                                    manifest["FirmwareBuild"], manifest["HardwareParameters"], False)
    require(result == parsed, "Stored long result differs from UART")
    require(result["iterations"] == 6000 and result["validation_run"] is validation, "Wrong long seed or iterations")
    require(result["crc_valid"] and result["modeled_duration_at_least_10s"], "Long CRC or duration gate failed")
    return result


def audit():
    for validation, compiled, source, physical in RUNS:
        manifest = json.loads((ROOT / "build/compiled" / compiled / "manifest.json").read_text(encoding="utf-8-sig"))
        require(manifest["SimulationPassed"] and manifest.get("CompletedUtc"), "Long simulation not complete: " + compiled)
    baseline_path = CPU / "build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    require(baseline["coremark_pair_hardware_passed"], "Baseline pair not qualified")
    baseline_result = next(run["result"] for run in baseline["runs"] if not run["result"]["validation_run"])
    baseline_measurement = Measurement(baseline_result["iterations"], baseline_result["cycles"], baseline_result["clock_hz"], baseline_result["lut_count"])
    require(baseline_measurement == Measurement(6000, 1885980108, 157500000, 9374), "Unexpected accepted baseline")
    runs = []
    for validation, compiled, source_id, physical_id in RUNS:
        source = ROOT / "build/pds" / source_id
        physical_directory = ROOT / "build/ila" / physical_id
        binding = audit_binding(source, validation)
        require(binding["clock_hz"] == 151200000, "Wrong candidate clock")
        physical = qualify(physical_directory, source=source, validation=validation, placement_seed=1)
        require(physical["physical_timing_passed"], "Full ILA timing failed: " + physical_id)
        directory = ROOT / "build/compiled" / compiled
        result = read_run(directory, binding, validation)
        reference = next(run["result"] for run in baseline["runs"] if run["result"]["validation_run"] is validation)
        for key in ("retired", "seed_crc", "final_crc", "profile"):
            require(result[key] == reference[key], "Long architectural behavior differs: " + key)
        runs.append({"validation_run": validation, "compiled_build": compiled, "physical_build": physical_id,
                     "result": result, "post_route_luts": physical["resources"]["post_route_luts"],
                     "setup_wns_ns": physical["setup_wns_ns"], "bitstream_sha256": physical["outputs_sha256"]["bitstream"],
                     "manifest_sha256": digest(directory / "manifest.json"), "binding": binding})
    performance = runs[0]
    result = performance["result"]
    measured = Measurement(result["iterations"], result["cycles"], result["clock_hz"], performance["post_route_luts"])
    policy = compare_score_resource_tradeoff(baseline_measurement, measured)
    receipt = {"schema": 1, "scope": "source-bound full-ILA PDS and paired long RTL qualification; not hardware scores",
               "local_pair_validated": True, "local_metric_gates_passed": policy["allowed"], "metric_policy": policy,
               "modeled_iterations_per_second": float(coremark(measured)),
               "modeled_execution_efficiency": float(measured.execution_efficiency),
               "modeled_resource_efficiency": float(measured.resource_efficiency),
               "hardware_validated": False, "full_score_qualified": False, "baseline_replaced": False,
               "baseline_receipt_sha256": digest(baseline_path), "runs": runs}
    destination = ROOT / "build/local-joint-score-resource-qualification.json"
    text = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == text, "Refusing to overwrite changed joint qualification")
    destination.write_text(text, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["local_metric_gates_passed"] else 2)
