import argparse
import json
from pathlib import Path

import audit_fetch_ila as physical_audit
import audit_fetch_scope_run as simulation_audit
from audit_fetch_inputs import ROOT, require, digest

SOURCE = ROOT / "build/pds/20260911-105255-fc9be582"
STAGE = ROOT / "build/ila/fetch-commit-scope-seed1"


def audit(directory):
    simulation = simulation_audit.audit(directory)
    physical = physical_audit.qualify(STAGE, SOURCE, placement_seed=1, scope=True)
    require(physical["physical_timing_passed"] is True and physical["constraints_met"] is True, "Application full-ILA timing failed")
    require(physical["ila"] == {"data_channels": 42, "trigger_channels": 33, "depth": 1024, "clock": "cpu_clk"}, "Application ILA incomplete")
    binding = physical["source_binding"]
    require(binding["firmware_sha256"] == simulation["firmware"]["firmware_sha256"] and binding["application_firmware"] == simulation["firmware"], "Application physical/simulation firmware differs")
    require(binding["clock_hz"] == physical["clock_hz"] == simulation["firmware"]["clock_hz"] == 153000000, "Application physical/simulation clock differs")
    reference = physical_audit.binding()
    require(binding["physical_source_hashes"] == reference["physical_source_hashes"] and binding["hardware_parameters"] == reference["hardware_parameters"], "Application and benchmark CPU configuration differ")
    result = {"schema": 1, "scope": "source-bound application RTL simulation and complete native ILA implementation; not hardware/electrical acceptance",
              "local_application_passed": True, "physical_build": STAGE.name, "simulation": simulation,
              "physical_qualification_sha256": digest(STAGE / "physical-qualification.json"),
              "clock_hz": physical["clock_hz"], "post_route_luts": physical["resources"]["post_route_luts"],
              "post_route_ffs": physical["resources"]["post_route_ffs"], "setup_wns_ns": physical["setup_wns_ns"],
              "ila": physical["ila"], "bitstream_sha256": physical["outputs_sha256"]["bitstream"],
              "hardware_validated": False, "electrical_review_closed": False, "full_score_qualified": False}
    destination = ROOT / "build/local-application-qualification.json"
    content = json.dumps(result, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == content, "Application qualification changed")
    destination.write_text(content, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.directory), indent=2))
