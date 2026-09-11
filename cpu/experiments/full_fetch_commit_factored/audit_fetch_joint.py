import json
from pathlib import Path

import audit_fetch_ila as physical_audit
import audit_fetch_long as long_audit
from frequency_promotion import Measurement
from frequency_target500 import compare_score_resource_tradeoff, coremark

ROOT = Path(__file__).resolve().parent
CPU = ROOT.parents[1]
require = physical_audit.require
digest = physical_audit.digest
load = physical_audit.load
STAGES = {
    False: ("20260911-095312-74f93c4b", "fetch-commit-seed1-native-wb"),
    True: ("20260911-101436-c57addf3", "fetch-commit-v1-seed1"),
}
BASELINE = Measurement(6000, 1885980108, 157500000, 9374)


def validate_join(run, manifest, physical, validation):
    result = run["result"]
    binding = physical["source_binding"]
    require(result["validation_run"] is validation and manifest["FirmwareBuild"]["ValidationRun"] is validation, "Wrong metric firmware role")
    require(result["iterations"] == 6000 and result["crc_valid"] is True and result["modeled_duration_at_least_10s"] is True, "Long metric prerequisites failed")
    require(physical["physical_timing_passed"] is True and physical["constraints_met"] is True, "Complete ILA timing failed")
    require(physical["ila"] == {"data_channels": 42, "trigger_channels": 33, "depth": 1024, "clock": "cpu_clk"}, "Incomplete metric ILA")
    require(result["clock_hz"] == physical["clock_hz"] == binding["clock_hz"] == 153000000, "Metric clock differs")
    require(manifest["MeasurementKind"] == "rtl_simulation_not_hardware" and manifest["SimulationPassed"] is True, "Wrong or incomplete metric simulation")
    require(manifest["FirmwareSha256"] == binding["firmware_sha256"] == manifest["FirmwareBuild"]["HexSha256"], "Metric firmware differs from physical image")
    require(manifest["HardwareParameters"] == binding["hardware_parameters"], "Metric hardware parameters differ")
    rtl = {name: checksum for name, checksum in manifest["SourceSnapshot"].items() if name.startswith("rtl/")}
    expected = {name: checksum for name, checksum in binding["physical_source_hashes"].items() if name.startswith("rtl/") and name != "rtl/rv32_board_top.sv"}
    require(len(binding["physical_source_hashes"]) == 20 and rtl == expected, "Metric RTL differs from complete physical system")
    luts = physical["resources"]["post_route_luts"]
    require(type(luts) is int and luts > 0, "Invalid full-system LUT denominator")
    return Measurement(result["iterations"], result["cycles"], result["clock_hz"], luts)


def audit():
    long_pair = long_audit.audit_long()
    baseline_path = CPU / "build/hardware/regfile-fanout-minimal-20260909-box5/hardware-coremark-qualification.json"
    baseline = load(baseline_path)
    require(baseline["coremark_pair_hardware_passed"] is True, "Accepted board baseline is not validated")
    baseline_performance = next(run["result"] for run in baseline["runs"] if run["result"]["validation_run"] is False)
    require(Measurement(baseline_performance["iterations"], baseline_performance["cycles"], baseline_performance["clock_hz"], baseline_performance["lut_count"]) == BASELINE, "Accepted baseline changed")
    require(long_pair["passed"] is True and len(long_pair["runs"]) == 2 and {run["result"]["validation_run"] for run in long_pair["runs"]} == {False, True}, "Incomplete metric long pair")
    runs = []
    for validation, (source_name, stage_name) in STAGES.items():
        run = next(item for item in long_pair["runs"] if item["result"]["validation_run"] is validation)
        directory = Path(run["directory"])
        manifest = load(directory / "manifest.json")
        require(digest(directory / "manifest.json") == run["manifest_sha256"], "Long manifest changed during joint audit")
        source, stage = ROOT / "build/pds" / source_name, ROOT / "build/ila" / stage_name
        physical = physical_audit.qualify(stage, source, placement_seed=1, validation=validation)
        measurement = validate_join(run, manifest, physical, validation)
        reference = next(item["result"] for item in baseline["runs"] if item["result"]["validation_run"] is validation)
        for key in ("retired", "seed_crc", "final_crc"):
            require(run["result"][key] == reference[key], "Long workload differs from accepted baseline: " + key)
        runs.append({"validation_run": validation, "compiled_build": directory.name, "physical_build": stage_name,
                     "result": run["result"], "post_route_luts": measurement.luts, "setup_wns_ns": physical["setup_wns_ns"],
                     "bitstream_sha256": physical["outputs_sha256"]["bitstream"], "manifest_sha256": run["manifest_sha256"],
                     "physical_qualification_sha256": digest(stage / "physical-qualification.json"), "binding": physical["source_binding"]})
    require(runs[0]["binding"]["physical_source_hashes"] == runs[1]["binding"]["physical_source_hashes"], "Performance and validation physical RTL differ")
    performance = runs[0]["result"]
    denominator = max(run["post_route_luts"] for run in runs)
    measured = Measurement(performance["iterations"], performance["cycles"], performance["clock_hz"], denominator)
    policy = compare_score_resource_tradeoff(BASELINE, measured)
    receipt = {"schema": 1, "scope": "own source-bound paired long RTL and complete native ILA physical results; not board qualification",
               "local_pair_validated": True, "local_metric_gates_passed": policy["allowed"], "metric_policy": policy,
               "modeled_iterations_per_second": float(coremark(measured)), "modeled_execution_efficiency": float(measured.execution_efficiency),
               "modeled_resource_efficiency": float(measured.resource_efficiency), "lut_denominator": denominator,
               "lut_denominator_policy": "maximum complete post-route LUT count across performance and validation images",
               "baseline_receipt_sha256": digest(baseline_path), "runs": runs,
               "hardware_validated": False, "full_score_qualified": False, "baseline_replaced": False}
    destination = ROOT / "build/local-joint-score-resource-qualification.json"
    content = json.dumps(receipt, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == content, "Joint qualification changed")
    destination.write_text(content, encoding="utf-8")
    return receipt


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["local_metric_gates_passed"] else 2)
