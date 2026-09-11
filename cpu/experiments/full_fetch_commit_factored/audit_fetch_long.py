import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path

import audit_fetch_inputs as inputs

firmware_audit = inputs.parent_audit.short_audit.firmware_audit

ROOT = Path(__file__).resolve().parent
digest = inputs.digest
require = inputs.require
load = inputs.load
portable = firmware_audit.portable
SPEC = importlib.util.spec_from_file_location("fetch_commit_long_checker", ROOT / "scripts/check_coremark.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def validate_terminal(build, manifest):
    require(manifest.get("SimulationPassed") is True and manifest.get("MeasurementKind") == "rtl_simulation_not_hardware", "Long simulation incomplete or mislabeled")
    require(manifest.get("SimulationBackend") == "Verilator 4.038 2020-07-11 rev v4.036-114-g0cd4a57ad", "Long simulator identity differs")
    started, finished = (datetime.fromisoformat(manifest[name]) for name in ("StartedUtc", "CompletedUtc"))
    require(started.utcoffset() is not None and finished.utcoffset() is not None and finished >= started, "Invalid long invocation interval")
    output = (build / "simulation.log").read_text(encoding="utf-8")
    terminals = re.findall(r"^PASS compiled RTL simulation cycles=(\d+) retired=(\d+)$", output, re.M)
    require(len(terminals) == 1 and not re.search(r"(?:FAIL|FATAL|watchdog|HOST_TIMEOUT)", output, re.I), "Long terminal result missing or failure reported")
    require(0 < int(terminals[0][0]) <= manifest["MaxCycles"] and int(terminals[0][1]) > 0, "Invalid long terminal counters")
    for name in ("compile.log", "simulation.log", "coremark.sim.uart", "result.json", "objects/Vrv32_soc"):
        path = build / name
        require(path.is_file() and path.stat().st_size > 0 and started.timestamp() - 2 <= path.stat().st_mtime <= finished.timestamp() + 2, "Long output outside invocation or missing: " + name)
    return {"total_simulation_cycles": int(terminals[0][0]), "total_retired": int(terminals[0][1]), "simulation_log_sha256": digest(build / "simulation.log")}


def audit_long():
    sources = inputs.audit_inputs()
    firmware_audit.audit_firmware()
    candidates = []
    for path in (ROOT / "build/compiled").glob("*/manifest.json"):
        manifest = load(path)
        if manifest.get("SimulationPassed") is True and manifest["FirmwareBuild"]["Iterations"] == 6000:
            candidates.append((path.parent, manifest))
    require(len(candidates) == 2 and {manifest["FirmwareBuild"]["ValidationRun"] for _, manifest in candidates} == {False, True}, "Expected exactly one completed long run per seed")
    expected_sources = {name: checksum for name, checksum in sources["physical_source_hashes"].items() if name.startswith("rtl/") and name != "rtl/rv32_board_top.sv"}
    expected_sources.update({name: sources["support_scripts"][name] for name in ("sim/coremark_compiled.cpp", "scripts/run_coremark_compiled.py", "scripts/check_coremark.py")})
    parameters = inputs.parent_audit.binding()["hardware_parameters"]
    results = []
    for build, manifest in candidates:
        terminal = validate_terminal(build, manifest)
        validation = manifest["FirmwareBuild"]["ValidationRun"]
        name = "coremark_v" + str(int(validation)) + "_i6000_p2700000_f153000000_rv32gcc_rv32im_O3_unroll_relax"
        firmware = load(inputs.PARENT / "build" / (name + ".build.json"))
        require(manifest["FirmwareBuild"] == firmware and manifest["FirmwareSha256"] == firmware["HexSha256"] == digest(build / "firmware.hex"), "Long firmware binding differs")
        require(manifest["SourceSnapshot"] == expected_sources and len(expected_sources) == 18, "Incomplete or changed long source inventory")
        for relative, checksum in expected_sources.items():
            require(digest(build / "source" / relative) == checksum == digest(ROOT / relative), "Captured long source differs")
        require(manifest["ConfigurationInput"] == load(ROOT / "configuration.json") and manifest["HardwareParameters"] == parameters, "Long configuration differs")
        require(manifest["SimulationClockHz"] == 100000000 and manifest["UartModelClockHz"] == 3200 and manifest["MaxCycles"] == 6000000000, "Wrong simulation clock or limit")
        require(portable(manifest["BuildDirectory"]) == portable(build) and manifest.get("CompletedUtc"), "Long completion or build identity missing")
        ordered_sources = [build / "source" / relative for relative in sorted(expected_sources) if relative.startswith("rtl/")]
        ordered_sources.append(build / "source/sim/coremark_compiled.cpp")
        command = ["/usr/bin/verilator", "--cc", "--exe", "--build", "--Wall", "-Wno-fatal", "-j", "2", "--top-module", "rv32_soc", "--Mdir", portable(build / "objects"),
                   "-CFLAGS", "-O3 -std=c++14", "-GCLOCK_HZ=3200", "-GBAUD=100", '-GINIT_FILE="' + portable(build / "firmware.hex") + '"']
        command += ["-G" + name + "=" + str(value) for name, value in parameters.items()]
        command += list(map(portable, ordered_sources))
        require(manifest["CompileCommand"] == command, "Long compile command differs")
        require(digest(build / "objects/Vrv32_soc") == manifest["ExecutableSha256"], "Long executable changed")
        require(digest(build / "coremark.sim.uart") == manifest["UartSha256"] and digest(build / "result.json") == manifest["ResultSha256"], "Long result hashes differ")
        result = checker.parse_result((build / "coremark.sim.uart").read_text(encoding="ascii"), allow_short=False, expected_config=0x0e8e96fd, expected_clock_hz=153000000)
        for key in tuple(result):
            if key.startswith("iterations_per_second"):
                del result[key]
        result["modeled_duration_at_least_10s"] = result.pop("reportable_duration")
        result["measurement_kind"] = "rtl_simulation_not_hardware"
        require(result == load(build / "result.json"), "Long raw UART and stored result differ")
        require(result["iterations"] == 6000 and result["validation_run"] is validation, "Wrong long seed or iterations")
        require(result["modeled_duration_at_least_10s"] is True, "Long run duration is not reportable")
        results.append({"directory": str(build), "manifest_sha256": digest(build / "manifest.json"), "result": result, "terminal": terminal})
    performance = next(run["result"] for run in results if not run["result"]["validation_run"])
    score = performance["iterations"] * performance["clock_hz"] / performance["cycles"]
    return {"schema": 1, "passed": True, "scope": "own paired source-bound 6000-iteration RTL results; not full-system physical or board qualification",
            "runs": results, "modeled_iterations_per_second": score,
            "modeled_execution_efficiency": score / (performance["clock_hz"] / 1000000),
            "resource_efficiency": None, "hardware_validated": False, "full_score_qualified": False}


if __name__ == "__main__":
    result = audit_long()
    (ROOT / "build/long-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
