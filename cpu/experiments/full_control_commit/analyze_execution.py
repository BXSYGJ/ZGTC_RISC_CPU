import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
from load_use_profile import file_hash, firmware_image, load_json, require, trace_records
from retirement_gap_profile import summarize_records


def main():
    directory = ROOT / "build/execution-profile-current"
    report = load_json(directory / "results.json")
    for field, name in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json"),
                        ("executable_sha256", "objects/Vrv32_soc"), ("uart_sha256", "uart.log"), ("invocation_sha256", "invocation.json")):
        require(file_hash(directory / name) == report[field], "Profile artifact changed: " + name)
    invocation = load_json(directory / "invocation.json")
    require(file_hash(directory / "firmware.hex") == invocation["firmware_sha256"], "Profile firmware changed")
    for relative, expected in invocation["inputs"].items():
        require(file_hash(directory / "source" / relative) == expected, "Observed source changed: " + relative)
        if relative != "sim/coremark_compiled.cpp":
            require(file_hash(ROOT / relative) == expected, "Current source changed: " + relative)
    metadata = load_json(directory / "uart.log.retire.json")
    require(report["passed"] is True and metadata == report["metadata"], "Profile result metadata mismatch")
    summary = summarize_records(trace_records(directory / "uart.log.retire.bin", metadata, firmware_image(directory / "firmware.hex")))
    require(summary["cycles"] == report["result"]["cycles"] and summary["records"] == report["records"], "Gap profile boundary mismatch")
    summary["profile_report_sha256"] = file_hash(directory / "results.json")
    summary["analyzer_sha256"] = file_hash(Path(__file__))
    (directory / "gap-analysis.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"records": summary["records"], "cycles": summary["cycles"],
                      "extra_cycles": summary["extra_cycles_above_one_per_interval"],
                      "axes": summary["axes"], "top_transitions": summary["transitions"][:12]}, indent=2))


if __name__ == "__main__":
    main()

