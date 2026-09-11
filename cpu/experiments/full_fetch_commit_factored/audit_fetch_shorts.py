import importlib.util
import json
import re
from pathlib import Path

import audit_fetch_inputs as inputs

firmware_audit = inputs.parent_audit.short_audit.firmware_audit

ROOT = Path(__file__).resolve().parent
digest = inputs.digest
require = inputs.require
load = inputs.load
portable = firmware_audit.portable
SPEC = importlib.util.spec_from_file_location("fetch_commit_checker", ROOT / "scripts/check_coremark.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def audit_shorts():
    sources = inputs.audit_inputs()
    firmware_audit.audit_firmware()
    candidates = []
    for path in (ROOT / "build/compiled").glob("*/manifest.json"):
        manifest = load(path)
        if manifest.get("SimulationPassed") is True and manifest["FirmwareBuild"]["Iterations"] == 10:
            candidates.append((path.parent, manifest))
    require(len(candidates) == 2 and {manifest["FirmwareBuild"]["ValidationRun"] for _, manifest in candidates} == {False, True}, "Expected exactly one completed short run per seed")
    expected_sources = {name: checksum for name, checksum in sources["physical_source_hashes"].items() if name.startswith("rtl/") and name != "rtl/rv32_board_top.sv"}
    expected_sources.update({name: sources["support_scripts"][name] for name in ("sim/coremark_compiled.cpp", "scripts/run_coremark_compiled.py", "scripts/check_coremark.py")})
    parameters = inputs.parent_audit.binding()["hardware_parameters"]
    parent_pair = inputs.parent_audit.short_audit.audit_shorts()
    results = []
    for build, manifest in candidates:
        validation = manifest["FirmwareBuild"]["ValidationRun"]
        name = "coremark_v" + str(int(validation)) + "_i10_f153000000_rv32gcc_rv32im_O3_unroll_relax"
        firmware = load(inputs.PARENT / "build" / (name + ".build.json"))
        require(manifest["FirmwareBuild"] == firmware and manifest["FirmwareSha256"] == firmware["HexSha256"] == digest(build / "firmware.hex"), "Short firmware binding differs")
        require(manifest["SourceSnapshot"] == expected_sources and len(expected_sources) == 18, "Incomplete or changed short source inventory")
        for relative, checksum in expected_sources.items():
            require(digest(build / "source" / relative) == checksum == digest(ROOT / relative), "Captured short source differs")
        require(manifest["ConfigurationInput"] == load(ROOT / "configuration.json") and manifest["HardwareParameters"] == parameters, "Short configuration differs")
        require(manifest["SimulationClockHz"] == 100000000 and manifest["UartModelClockHz"] == 3200 and manifest["MaxCycles"] == 10000000, "Wrong simulation clock or limit")
        require(portable(manifest["BuildDirectory"]) == portable(build) and manifest.get("CompletedUtc"), "Short completion or build identity missing")
        ordered_sources = [build / "source" / relative for relative in sorted(expected_sources) if relative.startswith("rtl/")]
        ordered_sources.append(build / "source/sim/coremark_compiled.cpp")
        command = ["/usr/bin/verilator", "--cc", "--exe", "--build", "--Wall", "-Wno-fatal", "-j", "2", "--top-module", "rv32_soc", "--Mdir", portable(build / "objects"),
                   "-CFLAGS", "-O3 -std=c++14", "-GCLOCK_HZ=3200", "-GBAUD=100", '-GINIT_FILE="' + portable(build / "firmware.hex") + '"']
        command += ["-G" + name + "=" + str(value) for name, value in parameters.items()]
        command += list(map(portable, ordered_sources))
        require(manifest["CompileCommand"] == command, "Short compile command differs")
        require(digest(build / "objects/Vrv32_soc") == manifest["ExecutableSha256"], "Short executable changed")
        require(digest(build / "coremark.sim.uart") == manifest["UartSha256"] and digest(build / "result.json") == manifest["ResultSha256"], "Short result hashes differ")
        result = checker.parse_result((build / "coremark.sim.uart").read_text(encoding="ascii"), allow_short=True, expected_config=0x0e8e96fd, expected_clock_hz=153000000)
        for key in tuple(result):
            if key.startswith("iterations_per_second"):
                del result[key]
        result["modeled_duration_at_least_10s"] = result.pop("reportable_duration")
        result["measurement_kind"] = "rtl_simulation_not_hardware"
        require(result == load(build / "result.json"), "Short raw UART and stored result differ")
        require(result["iterations"] == 10 and result["validation_run"] is validation, "Wrong short seed or iterations")
        previous_run = next(run for run in parent_pair["runs"] if run["result"]["validation_run"] is validation)
        parent = Path(previous_run["directory"])
        previous = previous_run["result"]
        require((build / "coremark.sim.uart").read_bytes() == (parent / "coremark.sim.uart").read_bytes(), "Fetch factoring changes raw short UART")
        for field in ("cycles", "retired", "profile", "final_crc", "seed_crc"):
            require(result[field] == previous[field], "Fetch factoring alters short behavior: " + field)
        results.append({"directory": str(build), "manifest_sha256": digest(build / "manifest.json"), "parent_result_sha256": digest(parent / "result.json"), "result": result})
    return {"schema": 1, "passed": True, "scope": "two source-bound exact-enable short screens; not long score or physical timing", "runs": results}


if __name__ == "__main__":
    result = audit_shorts()
    (ROOT / "build/short-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
