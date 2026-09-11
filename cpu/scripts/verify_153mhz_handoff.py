import importlib.util
import json
from hashlib import sha256
from pathlib import Path

CPU = Path(__file__).resolve().parents[1]
EVIDENCE = CPU / "docs/evidence/153mhz-20260911"
CANDIDATE = CPU / "experiments/full_fetch_commit_factored"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest().upper()


def main():
    for relative, expected in load(EVIDENCE / "manifest.json")["sha256"].items():
        require(digest(EVIDENCE / relative) == expected, "Evidence changed: " + relative)
    specification = importlib.util.spec_from_file_location("release_coremark_checker", CANDIDATE / "scripts/check_coremark.py")
    checker = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(checker)
    qualification = load(EVIDENCE / "hardware-qualification.json")
    physical = load(EVIDENCE / "physical-summary.json")
    for relative, expected in qualification["source_sha256"].items():
        require(digest(CANDIDATE / relative) == expected, "Qualified source changed: " + relative)
    require(qualification["provisional_validation_gates_passed"] is True and qualification["coremark_pair_hardware_passed"] is True, "Hardware gate absent")
    require(qualification["physical_ila_acquisition_required"] is False and qualification["electrical_review_closed"] is False, "Evidence boundary changed")
    for index, role in enumerate(("performance", "validation")):
        result = checker.parse_result((EVIDENCE / (role + ".uart")).read_text(), lut_count=9502, expected_config=0x0e8e96fd, expected_clock_hz=153000000)
        require(result == qualification["runs"][index]["result"] and result["validation_run"] is bool(index), "Published result differs")
        require(result["iterations"] == 6000 and result["reportable_duration"], "Short or wrong iteration count")
        require(physical[role]["resources"]["post_route_luts"] == 9502 and physical[role]["constraints_met"] is True, "Physical summary differs")
        require(physical[role]["bitstream_sha256"] == qualification["runs"][index]["bitstream_sha256"], "Bitstream identity differs")
    import ila_analyze
    profile = "FetchCommit153000MinimalRtl"
    ila_analyze.PROFILES[profile] = (153000000, "cpu_clk")
    ila_analyze.COMPACT_PROFILES += (profile,)
    reports = load(EVIDENCE / "local-ila-results.json")
    require(reports["hardware_validated"] is False, "Local capture mislabeled")
    for name in ("core_bench_list", "core_bench_matrix", "core_bench_state"):
        samples = ila_analyze.read_capture(EVIDENCE / (name + ".csv"), profile)
        require(len(samples) == 1024 and reports["algorithm_windows"][name]["temporal_pairs_checked"] == 1023, "Incomplete ILA capture")
        require(all(not sample["mem_fire"] or sample["mem_valid"] for sample in samples), "MEM without valid")
        require(all(not following["wb_valid"] or previous["mem_fire"] for previous, following in zip(samples, samples[1:])), "WB without preceding MEM")
    require(load(EVIDENCE / "device-release.json")["released"] is True, "Release record missing")
    print("PASS published 153 MHz handoff: source hashes, hardware V0/V1, complete-system area, three local ILA windows")
    print("This checks archived evidence consistency, not a new hardware run or independent physical/electrical certification.")


if __name__ == "__main__":
    main()
