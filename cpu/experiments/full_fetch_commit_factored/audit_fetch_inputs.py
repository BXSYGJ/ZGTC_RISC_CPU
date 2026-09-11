import json
from pathlib import Path

from prepare_fetch import ROOT, PARENT, digest, require, load, validate_delta, parent_audit


def audit_inputs():
    delta = validate_delta()
    parent = parent_audit.binding()
    record = load(ROOT / "source-inputs.json")
    require(record["parent"] == str(PARENT) and record["parent_source_input_sha256"] == digest(PARENT / "source-inputs.json"), "Parent inventory changed")
    expected = dict(parent["physical_source_hashes"])
    expected["rtl/rv32_core.sv"] = delta["candidate_core_sha256"]
    require(record["physical_source_hashes"] == expected and len(expected) == 20, "Wrong complete-source inventory")
    for relative, checksum in expected.items():
        require(digest(ROOT / relative) == checksum, "Physical input changed: " + relative)
    support = {relative: digest(PARENT / relative) for relative in load(PARENT / "source-inputs.json")["support_scripts"]}
    require(record["support_scripts"] == support, "Wrong support inventory")
    for relative, checksum in support.items():
        require(digest(ROOT / relative) == checksum, "Support input changed: " + relative)
    configuration = load(PARENT / "configuration.json")
    configuration["Purpose"] = "Exact fetch commit enable factoring in complete 153 MHz system; not qualified"
    require(load(ROOT / "configuration.json") == configuration and record["configuration_sha256"] == digest(ROOT / "configuration.json"), "Configuration changed")
    require(record["delta_sha256"] == digest(ROOT / "change-receipt.json") and record["generator_sha256"] == digest(ROOT / "prepare_fetch.py"), "Fetch delta or generator changed")
    return record


if __name__ == "__main__":
    print(json.dumps(audit_inputs(), indent=2))
