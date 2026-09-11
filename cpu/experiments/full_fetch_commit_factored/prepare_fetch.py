import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_timer_clock153000"
sys.path.insert(0, str(PARENT))
import audit_clock_ila as parent_audit

digest = parent_audit.digest
require = parent_audit.require
load = parent_audit.load


def validate_delta():
    record = load(ROOT / "change-receipt.json")
    original = PARENT / "rtl/rv32_core.sv"
    require(record["parent"] == PARENT.name and digest(original) == record["parent_core_sha256"], "Parent CPU changed")
    content = original.read_text(encoding="utf-8")
    require(len(record["substitutions"]) == 3, "Wrong fetch source delta")
    for before, after in record["substitutions"]:
        require(content.count(before) == 1, "Ambiguous fetch source delta")
        content = content.replace(before, after)
    candidate = ROOT / "rtl/rv32_core.sv"
    require(candidate.read_text(encoding="utf-8") == content and digest(candidate) == record["candidate_core_sha256"], "Unexpected fetch CPU changes")
    return record


def prepare():
    require(not (ROOT / "source-inputs.json").exists(), "Fetch project already staged")
    delta = validate_delta()
    parent = parent_audit.binding()
    physical = {}
    for relative, checksum in parent["physical_source_hashes"].items():
        original = PARENT / relative
        require(digest(original) == checksum, "Parent input changed")
        target = ROOT / relative
        if relative != "rtl/rv32_core.sv":
            require(not target.exists(), "Staging would overwrite an input")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
        physical[relative] = digest(target)
    require({name for name in physical if physical[name] != parent["physical_source_hashes"][name]} == {"rtl/rv32_core.sv"}, "Unexpected complete-system delta")
    support = {}
    for relative in load(PARENT / "source-inputs.json")["support_scripts"]:
        source, target = PARENT / relative, ROOT / relative
        require(not target.exists(), "Support input already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        support[relative] = digest(target)
    configuration = load(PARENT / "configuration.json")
    configuration["Purpose"] = "Exact fetch commit enable factoring in complete 153 MHz system; not qualified"
    (ROOT / "configuration.json").write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
    record = {"schema": 1, "scope": "complete 153 MHz parent with exact three CPU substitutions; no metric qualification",
              "parent": str(PARENT), "parent_source_input_sha256": digest(PARENT / "source-inputs.json"),
              "physical_source_hashes": physical, "support_scripts": support,
              "configuration_sha256": digest(ROOT / "configuration.json"), "delta_sha256": digest(ROOT / "change-receipt.json"),
              "generator_sha256": digest(Path(__file__)), "clock_hz": 153000000, "hardware_validated": False}
    (ROOT / "source-inputs.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("PASS complete fetch-factor project staged")


if __name__ == "__main__":
    prepare()
