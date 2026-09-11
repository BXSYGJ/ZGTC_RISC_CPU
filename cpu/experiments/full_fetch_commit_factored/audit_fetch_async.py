import argparse
import importlib.util
import json

import audit_fetch_ila as physical
from audit_fetch_inputs import ROOT, digest, require, load

CHECKER_PATH = ROOT.parent / "full_redirect_clock151200/audit_async_structure.py"
CHECKER_SHA256 = "E3D786523AE68796A45B7E503DB7DED314B067C18FBB66C6C2F89EAFB1D78513"
require(digest(CHECKER_PATH) == CHECKER_SHA256, "Reference synchronizer checker changed")
SPEC = importlib.util.spec_from_file_location("fetch_reference_async_structure", CHECKER_PATH)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)
STAGES = [("fetch-commit-seed1-native-wb", "20260911-095312-74f93c4b", False, False),
          ("fetch-commit-v1-seed1", "20260911-101436-c57addf3", True, False)]
APPLICATION = ("fetch-commit-scope-seed1", "20260911-105255-fc9be582", False, True)


def audit(include_application=False):
    require(type(include_application) is bool, "Invalid application selection")
    require(digest(CHECKER_PATH) == CHECKER_SHA256, "Reference synchronizer checker changed")
    reports = []
    for name, source_name, validation, scope in STAGES + ([APPLICATION] if include_application else []):
        stage = ROOT / "build/ila" / name
        bound = physical.binding(ROOT / "build/pds" / source_name, validation=validation, scope=scope)
        invocation = load(stage / "invocation.json")
        require(invocation["ExitCode"] == 0 and invocation.get("FinishedUtc"), "Native input implementation incomplete")
        netlist = stage / "netlist.v"
        require(digest(netlist) == invocation["Inputs"]["netlist.v"], "Native input netlist differs")
        require(digest(stage / "firmware.hex") == bound["firmware_sha256"] == invocation["Inputs"]["firmware.hex"], "Native firmware binding differs")
        report = checker.audit(netlist)
        report.update(stage=name, firmware_sha256=bound["firmware_sha256"], invocation_sha256=digest(stage / "invocation.json"))
        reports.append(report)
    result = {"schema": 1, "scope": "source-bound four-chain synthesized connectivity review only; not routed CDC or electrical acceptance",
              "checker_sha256": CHECKER_SHA256, "reports": reports, "hardware_validated": False, "electrical_review_closed": False}
    destination = ROOT / "build" / ("async-structure-all-images.json" if include_application else "async-structure-benchmark-pair.json")
    content = json.dumps(result, indent=2) + "\n"
    require(not destination.exists() or destination.read_text(encoding="utf-8") == content, "Synchronizer review changed")
    destination.write_text(content, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-application", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(audit(arguments.include_application), indent=2))
