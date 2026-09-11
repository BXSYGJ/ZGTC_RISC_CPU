import importlib.util
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HARDWARE = ROOT.parents[1] / "build/hardware/fetch-commit153000-20260911-box1"
SPEC = importlib.util.spec_from_file_location("fetch_hardware_checker", ROOT / "scripts/check_coremark.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def digest(path):
    from hashlib import sha256
    return sha256(path.read_bytes()).hexdigest().upper()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_packets(session, uart):
    packets = session["reads"]
    require(bool(packets), "Missing UART packets")
    previous = None
    joined = []
    for packet in packets:
        body = packet["body"]
        timestamp = datetime.fromisoformat(packet["at"].replace("Z", "+00:00"))
        require(previous is None or timestamp >= previous, "UART packet order changed")
        previous = timestamp
        require(packet["status"] == 200 and body["success"] is True, "UART transport failed")
        raw = bytes.fromhex(body["hex"])
        require(len(raw) == body["bytesRead"] and raw.decode("utf-8") == body["data"], "UART packet bytes differ")
        joined.append(body["data"])
    require("".join(joined) == uart, "UART evidence differs from packets")
    downloads = session["download"]
    require(len(downloads) == 1, "Expected one image download")
    download = downloads[0]
    require(download["status"] == 200 and download["body"]["success"] is True, "Download failed")
    data = download["body"]["data"]
    require(data["deviceId"] == 12 and data["tcpResult"]["burnResult"]["success"] is True, "Wrong device or failed burn")
    require(datetime.fromisoformat(download["at"].replace("Z", "+00:00")) <= datetime.fromisoformat(packets[0]["at"].replace("Z", "+00:00")), "UART predates image download")


def audit():
    runs = []
    sources = None
    stages = ("fetch-commit-seed1-native-wb", "fetch-commit-v1-seed1")
    simulations = ("20260911-102437-50412c5f", "20260911-105001-2a7db72e")
    for validation, (role, stage_name, simulation) in enumerate(zip(("performance", "validation"), stages, simulations)):
        stage = ROOT / "build/ila" / stage_name
        physical = load(stage / "physical-qualification.json")
        bitstream = stage / "generate_bitstream/pds_soc_top.sbit"
        session = load(HARDWARE / (role + "-r1-session.json"))
        uart_path = HARDWARE / (role + "-r1.uart")
        uart = uart_path.read_text(encoding="utf-8")
        validate_packets(session, uart)
        require(session["bitstream_sha256"] == physical["outputs_sha256"]["bitstream"] == digest(bitstream), "Physical image binding changed")
        require(physical["physical_timing_passed"] is True and physical["constraints_met"] is True, "Physical timing failed")
        require(physical["ila"] == {"data_channels": 42, "trigger_channels": 33, "depth": 1024, "clock": "cpu_clk"}, "Incomplete ILA")
        require(physical["resources"]["post_route_luts"] == 9502 and physical["resources"]["post_route_ffs"] == 5079, "Complete resource denominator differs")
        current = physical["source_binding"]["physical_source_hashes"]
        require(len(current) == 20 and all(digest(ROOT / name) == expected for name, expected in current.items()), "Current physical sources differ")
        require(sources is None or current == sources, "V0/V1 physical sources differ")
        sources = current
        result = checker.parse_result(uart, lut_count=9502, expected_config=0x0e8e96fd, expected_clock_hz=153000000)
        require(result["validation_run"] is bool(validation) and result["iterations"] == 6000 and result["reportable_duration"], "Wrong seed, iterations or duration")
        local = load(ROOT / "build/compiled" / simulation / "result.json")
        require(all(result[name] == local[name] for name in ("cycles", "retired", "profile", "seed_crc", "final_crc")), "Hardware and source-bound simulation differ")
        require(result == load(HARDWARE / (role + "-r1.result.json")), "Saved hardware result changed")
        runs.append({"role": role, "result": result, "bitstream_sha256": digest(bitstream), "uart_sha256": digest(uart_path), "session_sha256": digest(HARDWARE / (role + "-r1-session.json")), "physical_qualification_sha256": digest(stage / "physical-qualification.json")})
    scope_session = load(HARDWARE / "scope-smoke-session.json")
    scope_uart = (HARDWARE / "scope-smoke.uart").read_text(encoding="utf-8")
    validate_packets(scope_session, scope_uart)
    scope_bitstream = ROOT / "build/ila/fetch-commit-scope-seed1/generate_bitstream/pds_soc_top.sbit"
    require(scope_session["bitstream_sha256"] == digest(scope_bitstream), "Scope image differs")
    require(all(marker in scope_uart for marker in ("EMPTY\n", "ARMED\n", "TIMEOUT\n")), "Scope smoke incomplete")
    pipeline = load(ROOT / "build/ila-pipeline-rtl/fetch-commit153000/results.json")
    require(pipeline["hardware_validated"] is False and len(pipeline["algorithm_windows"]) == 3, "ILA evidence mislabeled")
    require(all(window["samples"] == 1024 and window["temporal_pairs_checked"] == 1023 for window in pipeline["algorithm_windows"].values()), "Incomplete local ILA")
    require(load(HARDWARE / "device-release.json")["released"] is True, "Device not released")
    result = {"schema": 1, "date": "2026-09-11", "scope": "Provisional completion under user-approved local ILA plus remote bring-up criteria; not electrical or exhaustive certification", "device": {"id": 12, "name": "Experiment box 1", "model": "PG2L200H"}, "coremark_pair_hardware_passed": True, "local_algorithm_ila_passed": True, "physical_ila_acquisition_required": False, "physical_ila_acquisition_passed": False, "scope_hardware_smoke_passed": True, "scope_hardware_waveform_capture_passed": False, "electrical_review_closed": False, "provisional_validation_gates_passed": True, "device_released": True, "clock_kind": "Configured PLL clock, not independently measured", "runs": runs, "source_sha256": sources, "ila_results_sha256": digest(ROOT / "build/ila-pipeline-rtl/fetch-commit153000/results.json"), "scope_session_sha256": digest(HARDWARE / "scope-smoke-session.json"), "auditor_sha256": digest(Path(__file__))}
    (HARDWARE / "hardware-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    audit()
