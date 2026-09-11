import json

from audit_binding import ROOT, audit as audit_binding, digest, require
from audit_scope_run import audit as audit_runtime
from audit_async_structure import audit as audit_async
from qualify_full_ila import qualify

RUNTIME = ROOT / "build/scope-current/20260911-010153-3367fed2"
SOURCE = ROOT / "build/pds/20260911-003942-efd1764f"
STAGE = ROOT / "build/ila/20260911-redirect-clock151200-scope-seed1"


def validate_pair(runtime, binding, physical, snapshot):
    require(runtime["simulation_passed"] is True and runtime["hardware_validated"] is False, "Application runtime incomplete or mislabeled")
    require(physical["physical_timing_passed"] is True and physical["hardware_validated"] is False, "Application timing incomplete or mislabeled")
    require(binding["clock_hz"] == physical["clock_hz"] == runtime["firmware"]["clock_hz"] == 151200000, "Application clock mismatch")
    require(runtime["firmware"] == physical["application_firmware"], "Application firmware metadata mismatch")
    require(binding["physical_firmware_sha256"] == runtime["firmware"]["firmware_sha256"] == physical["inputs_sha256"]["firmware.hex"], "Application firmware bytes mismatch")
    require(binding["physical_source_hashes"] == snapshot["source_snapshot"]["Files"], "Application RTL source mismatch")
    require(binding["board_parameters"] == snapshot["physical_parameters"], "Application hardware parameters mismatch")
    require(physical["ila"] == {"data_channels": 42, "trigger_channels": 33, "depth": 1024, "clock": "cpu_clk"}, "Application ILA function changed")


def audit():
    runtime = audit_runtime(RUNTIME)
    binding = audit_binding(SOURCE, scope=True)
    physical = qualify(STAGE, source=SOURCE, scope=True, placement_seed=1)
    snapshot = json.loads((RUNTIME / "manifest.json").read_text(encoding="utf-8"))
    validate_pair(runtime, binding, physical, snapshot)
    structural = audit_async(STAGE / "netlist.v")
    require(structural["netlist_sha256"] == physical["inputs_sha256"]["netlist.v"], "Application structural netlist mismatch")
    result = {"schema": 1, "scope": "source-bound scope RTL runtime and full-ILA physical implementation; not board or electrical qualification",
              "local_application_pair_passed": True, "hardware_validated": False, "electrical_qualified": False,
              "runtime": runtime, "binding": binding, "physical": physical, "bounded_async_structure": structural}
    output = ROOT / "build/local-application-qualification.json"
    text = json.dumps(result, indent=2) + "\n"
    require(not output.exists() or output.read_text(encoding="utf-8") == text, "Refusing to overwrite changed application qualification")
    output.write_text(text, encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
