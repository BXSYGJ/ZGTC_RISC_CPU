import json
import re
from pathlib import Path

from prepare_physical import digest, require
from run_external_isa import ARCHIVE_SHA256, REVISION

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
OUTPUT = ROOT / "build/external-isa"
CONFIGURATIONS = {"p0_c0_s4", "p1_c0_s4", "p0_c1_s1", "p1_c1_s4"}
REJECTIONS = {"negative_fail": "ISA failure testnum=99", "negative_trap": "ISA unexpected trap cause=2",
              "negative_timeout": "ISA watchdog expired", "ma_data": "ISA unexpected trap cause=4"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def validate_coverage(result, tests, suite):
    require(result["status"] == "passed" and result["suite"] == suite, "Suite is not complete")
    require(result["tests"] == tests and len(set(tests)) == len(tests) and tests, "Wrong upstream test set")
    expected = {(name, config) for name in tests for config in CONFIGURATIONS}
    observed = [(entry["name"], entry["configuration"]) for entry in result["results"]]
    require(len(observed) == len(expected) and set(observed) == expected, "Missing or duplicate ISA test/configuration pair")
    controls = result["negative_controls"]
    require(len(controls) == 4 and {entry["name"]: entry["expected_rejection"] for entry in controls} == REJECTIONS, "Missing or wrong rejection controls")


def audit(output=OUTPUT):
    record = read_json(output / "invocation.json")
    require(record["passed"] is True and set(record["suites"]) == {"rv32ui", "rv32um"}, "Incomplete external ISA run")
    require(record["revision"] == REVISION and record["archive_sha256"] == ARCHIVE_SHA256, "Wrong upstream provenance")
    require(record["runner_sha256"] == digest(ROOT / "run_external_isa.py") == digest(output / "runner-original.py"), "External runner changed")
    project = output / "project"
    inventory = read_json(ROOT / "build/physical-project-complete-inputs.json")["source_hashes"]
    require(set(inventory).issubset(record["inputs"]) and len(inventory) == 20, "Incomplete physical inputs")
    for relative, expected in record["inputs"].items():
        require(digest(project / relative) == expected, "Captured ISA input changed")
        if relative in inventory:
            current = ROOT / Path(relative).name if relative in ("rtl/rv32_core.sv", "rtl/rv32_btb.sv") else BASE / relative
            require(digest(current) == inventory[relative] == expected, "Current RTL differs from tested candidate")
        else:
            require(digest(BASE / relative) == expected, "Current ISA adapter differs")
    for filename, expected in record["outputs"].items():
        require(digest(output / filename) == expected, "External invocation output changed")
    summary = {}
    for suite, evidence in record["suites"].items():
        directory = output / suite
        result = read_json(directory / "results.json")
        require(digest(directory / "results.json") == evidence["results_sha256"], "Suite result changed")
        for filename, expected in evidence["artifact_sha256"].items():
            require(digest(directory / filename) == expected, "ISA artifact changed: " + filename)
        for relative, expected in result["upstream_inputs"].items():
            require(digest(output / "upstream" / relative) == expected.upper(), "Upstream source changed")
        makefrag = (output / "upstream/isa" / suite / "Makefrag").read_text()
        match = re.search(suite + r"_sc_tests\s*=\s*\\\n(.*?)\n\n", makefrag, re.S)
        require(match is not None, "Unrecognized upstream test list")
        tests = [name for name in match.group(1).replace(chr(92), " ").split() if name != "ma_data"]
        validate_coverage(result, tests, suite)
        for entry in result["results"]:
            name = entry["name"]
            require(digest(directory / (name + ".hex")) == entry["hex_sha256"].upper(), "ISA firmware differs")
            text = (directory / (name + "_" + entry["configuration"] + ".log")).read_text()
            require(len(re.findall(r"^PASS ISA name=" + re.escape(name) + r"\s", text, re.M)) == 1, "Missing or ambiguous raw ISA pass")
        for name, rejection in REJECTIONS.items():
            text = (directory / (name + ".log")).read_text()
            require(rejection in text and "PASS ISA" not in text, "Raw negative-control evidence differs")
        summary[suite] = {"tests": len(tests), "runs": len(result["results"]), "negative_controls": 4, "excluded": result["excluded"]}
    result = {"schema": 1, "passed": True, "suites": summary, "invocation_sha256": digest(output / "invocation.json"),
              "auditor_sha256": digest(Path(__file__)), "scope": "pinned external ISA tests and rejection controls; not complete ISA certification or hardware validation"}
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
