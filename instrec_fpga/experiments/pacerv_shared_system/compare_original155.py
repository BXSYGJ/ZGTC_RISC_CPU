"""Test Original155 with the current memories and its original fetch-pair convention."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE = Path(
    "D:/AAAFPGA/Current_Paper_and_Sub7000_Core_Releases_20261012/cores/Original_155250"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    args = parser.parse_args()
    release = args.release.resolve(strict=True)
    recipe = json.loads((release / "recipe.json").read_text(encoding="utf-8-sig"))
    if recipe["release"] != "Original_155250" or recipe["clock_hz"] != 155250000:
        raise ValueError("Expected the frozen Original_155250 release recipe")
    current = ROOT / "src/cpu/vendor/pacerv_h3"
    provenance = json.loads((current / "PROVENANCE.json").read_text(encoding="utf-8-sig"))
    wrapper = ROOT / "src/cpu/rv32_cpu_subsys.sv"
    firmware = ROOT / "src/cpu/prog.hex"
    monitored = [wrapper, firmware, *(current / x["file"] for x in provenance["files"])]
    before = {str(p.relative_to(ROOT)): sha(p) for p in monitored}
    output = ROOT / "build/pacerv_shared_system/original155_same_wrapper"
    vendor = output / "rtl"
    vendor.mkdir(parents=True, exist_ok=True)
    records = []
    for item in provenance["files"]:
        source = release / "source/rtl" / item["file"]
        routed_source = release / "physical/V0/inputs/rtl" / item["file"]
        if sha(source) != sha(routed_source):
            raise RuntimeError("Archive source differs from routed source: " + source.name)
        target = vendor / source.name
        shutil.copy2(source, target)
        records.append({"file": source.name, "sha256": sha(target)})
    (vendor / "PROVENANCE.json").write_text(json.dumps({
        "source": str(release), "recipe_sha256": sha(release / "recipe.json"),
        "physical_source_match": True, "files": records,
    }, indent=2) + "\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "original155_checks", ROOT / "sim/experiments/pacerv_integration/run_pacerv_checks.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.VENDOR = vendor
    module.OUT = output
    adapter = output / "rv32_cpu_subsys.sv"
    original_wrapper = wrapper.read_text(encoding="utf-8")
    pair_port = "        .i_req_pair_address(i_req_pair_address),\n"
    if original_wrapper.count(pair_port) != 1:
        raise RuntimeError("Expected one H3 pair-address port")
    adapted = original_wrapper.replace(pair_port, "")
    anchor = "    wire [31:0] i_req_address, i_req_pair_address;\n"
    if adapted.count(anchor) != 1:
        raise RuntimeError("Expected one fetch-address declaration")
    adapted = adapted.replace(anchor, anchor +
        "    assign i_req_pair_address = {i_req_address[31:3], 1'b1, 2'b0};\n")
    adapter.write_text(adapted, encoding="utf-8")
    tests = ROOT / "sim/experiments/pacerv_integration"
    checks = {"results": [], "passed": False}
    code = 1
    try:
        result = module.run([sys.executable, tests / "build_pacerv_directed.py"])
        checks["results"].append(result)
        if result["exit_status"]:
            raise RuntimeError(result["output"])
        rtl = [vendor / item["file"] for item in records]
        for top, token, timeout in [
            ("tb_pacerv_directed", "PACERV_DIRECTED_PASS", 30),
            ("tb_pacerv_backpressure", "PACERV_BACKPRESSURE_PASS", 30),
            ("tb_pacerv_audio", "RESULT: PASS", 300),
        ]:
            binary = output / (top + ".vvp")
            result = module.run([shutil.which("iverilog"), "-g2012", "-s", top,
                                 "-o", binary, tests / (top + ".sv"), adapter, *rtl])
            checks["results"].append(result)
            if result["exit_status"]:
                raise RuntimeError(result["output"])
            result = module.run([shutil.which("vvp"), "-i", binary], timeout=timeout)
            checks["results"].append(result)
            (output / (top + ".log")).write_text(result["output"], encoding="utf-8")
            print(result["output"], end="", flush=True)
            if result["exit_status"] or token not in result["output"]:
                raise RuntimeError(top + " did not pass")
        checks["passed"] = True
        code = 0
    finally:
        (output / "pacerv_checks.json").write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
        unchanged = all(sha(ROOT / key) == value for key, value in before.items())
        report = {
            "scope": "Same memories, firmware and tests; Original155 fetch-pair address adapter; RTL only",
            "release": recipe["release"], "archive_clock_hz": recipe["clock_hz"],
            "archive_clock_is_not_a_new_system_measurement": True,
            "current_inputs_sha256": before, "live_inputs_unchanged": unchanged,
            "physical_source_match": True, "exit_status": code,
            "adapter_sha256": sha(adapter),
            "adapter_changes": "Remove pair-address output port; derive the original aligned eight-byte pair address",
            "checks": str(output / "pacerv_checks.json"),
        }
        (output / "COMPARISON.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not unchanged:
            raise RuntimeError("Live integration sources changed during isolated comparison")
    print("ORIGINAL155_SAME_WRAPPER_PASS live_inputs_unchanged=1 cases=3")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
