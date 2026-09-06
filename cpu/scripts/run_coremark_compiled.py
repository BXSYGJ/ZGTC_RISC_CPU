import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from check_coremark import parse_result


BINARY_PARAMETERS = {
    "Predictor": "ENABLE_PREDICTOR", "CacheEnabled": "ENABLE_CACHE",
    "LoadUseBubble": "LOAD_USE_BUBBLE", "FastICacheHit": "FAST_ICACHE_HIT",
    "FastDCacheRead": "FAST_DCACHE_READ", "FastDCacheWrite": "FAST_DCACHE_WRITE",
    "FetchOverlap": "FETCH_OVERLAP", "DataOverlap": "DATA_OVERLAP",
    "EarlyDRequest": "EARLY_D_REQUEST", "EnableM": "ENABLE_M",
}


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest().upper()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def hardware_parameters(configuration):
    parameters = {}
    for field, parameter in BINARY_PARAMETERS.items():
        value = configuration[field]
        if type(value) is not int or value not in (0, 1):
            raise ValueError(f"Invalid binary hardware parameter: {field}")
        parameters[parameter] = value
    for field, parameter in (("CacheSetBits", "CACHE_SET_BITS"),
                             ("ICacheSetBits", "ICACHE_SET_BITS"),
                             ("BtbIndexBits", "BTB_INDEX_BITS")):
        value = configuration.get(field, configuration["CacheSetBits"]) if field == "ICacheSetBits" else configuration[field]
        if type(value) is not int or not 1 <= value <= 8:
            raise ValueError(f"Invalid width hardware parameter: {field}")
        parameters[parameter] = value
    return parameters


def configuration_word(parameters):
    instruction_width = parameters["ICACHE_SET_BITS"]
    data_width = parameters["CACHE_SET_BITS"]
    instruction_code = instruction_width if instruction_width != data_width else 0
    predictor_width = parameters["BTB_INDEX_BITS"]
    predictor_code = predictor_width if predictor_width != 4 else 0
    enabled = parameters["ENABLE_CACHE"]
    word = 0x0e020000 | (instruction_code << 12) | (predictor_code << 20) | (data_width << 8)
    word |= parameters["ENABLE_PREDICTOR"] | ((1 - enabled) << 1)
    word |= parameters["LOAD_USE_BUBBLE"] << 2
    word |= (parameters["FAST_ICACHE_HIT"] & enabled) << 3
    word |= parameters["ENABLE_M"] << 4
    word |= parameters["FETCH_OVERLAP"] << 5
    word |= (parameters["FAST_DCACHE_READ"] & enabled) << 6
    word |= parameters["EARLY_D_REQUEST"] << 7
    word |= parameters["DATA_OVERLAP"] << 18
    word |= (parameters["FAST_DCACHE_WRITE"] & enabled) << 19
    return word


def validate_firmware(firmware_path, firmware, parameters):
    words = firmware_path.read_text(encoding="ascii").splitlines()
    if len(words) != 16384 or any(re.fullmatch(r"[0-9a-fA-F]{8}", word) is None for word in words):
        raise ValueError("Firmware must have exactly 16384 hexadecimal words")
    if file_hash(firmware_path) != firmware["HexSha256"].upper():
        raise ValueError("Firmware bytes do not match build manifest")
    if type(firmware["EnableM"]) is not int or firmware["EnableM"] not in (0, 1):
        raise ValueError("Invalid firmware M-extension metadata")
    if firmware["EnableM"] and not parameters["ENABLE_M"]:
        raise ValueError("RV32IM firmware requires M-enabled hardware")
    if type(firmware["Iterations"]) is not int or not 1 <= firmware["Iterations"] <= 10000000:
        raise ValueError("Invalid firmware iteration count")
    if type(firmware["ValidationRun"]) is not bool:
        raise ValueError("Invalid firmware seed selection")
    if type(firmware["ClockHz"]) is not int or firmware["ClockHz"] <= 0:
        raise ValueError("Invalid firmware clock metadata")


def validate_configuration_binding(configuration, firmware, sources):
    if "SourceSnapshot" not in configuration:
        return False
    snapshot = configuration["SourceSnapshot"]
    if not isinstance(snapshot, dict) or snapshot.get("Schema") != 1 or not isinstance(snapshot.get("Files"), dict):
        raise ValueError("Invalid implementation source snapshot")
    for relative, actual in sources.items():
        if relative.startswith("rtl/"):
            expected = snapshot["Files"].get(relative)
            if not isinstance(expected, str) or expected.upper() != actual:
                raise ValueError(f"Implementation RTL differs from compiled input: {relative}")
    if configuration.get("ClockHz") != firmware["ClockHz"]:
        raise ValueError("Implementation clock differs from firmware")
    if configuration.get("FirmwareSha256", "").upper() != firmware["HexSha256"].upper():
        raise ValueError("Implementation firmware differs from compiled input")
    return True


def check_simulation_result(text, firmware, parameters, allow_short):
    result = parse_result(text, allow_short=allow_short,
                          expected_config=configuration_word(parameters),
                          expected_clock_hz=firmware["ClockHz"])
    if result["iterations"] != firmware["Iterations"] or result["validation_run"] != firmware["ValidationRun"]:
        raise ValueError("UART iteration or seed differs from supplied firmware manifest")
    for key in tuple(result):
        if key.startswith("iterations_per_second"):
            del result[key]
    result["modeled_duration_at_least_10s"] = result.pop("reportable_duration")
    result["measurement_kind"] = "rtl_simulation_not_hardware"
    return result


def verify_artifacts(build, manifest):
    for relative, expected in manifest["SourceSnapshot"].items():
        if file_hash(build / "source" / relative) != expected:
            raise ValueError(f"Source snapshot changed: {relative}")
    if file_hash(build / "firmware.hex") != manifest["FirmwareSha256"]:
        raise ValueError("Firmware snapshot changed")
    if file_hash(build / "objects" / "Vrv32_soc") != manifest["ExecutableSha256"]:
        raise ValueError("Compiled executable changed")


def validate_compiler_warnings(text, source):
    memory_source = source / "rtl" / "rv32_burst_ram.sv"
    lines = memory_source.read_text(encoding="utf-8").splitlines()
    matching_lines = [index + 1 for index, line in enumerate(lines)
                      if line.strip() == 'if(INIT_FILE!="") $readmemh(INIT_FILE,memory);']
    for warning in re.findall(r"^%Warning[^\n]*", text, flags=re.MULTILINE):
        accepted = False
        for line_number in matching_lines:
            prefix = re.escape(f"%Warning-WIDTH: {memory_source}:{line_number}:")
            suffix = re.escape(" bits on the RHS, but RHS's CONST '?1?h0' generates 1 bits.")
            if re.fullmatch(prefix + r"\d+: Operator NEQ expects \d+" + suffix, warning):
                accepted = True
        if not accepted:
            raise ValueError(f"Unapproved Verilator warning: {warning}")


def execute(configuration_path, firmware_manifest_path, max_cycles, allow_short):
    root = Path(__file__).resolve().parents[1]
    configuration = load_json(configuration_path)
    firmware = load_json(firmware_manifest_path)
    if not firmware_manifest_path.name.endswith(".build.json"):
        raise ValueError("Firmware manifest must end with .build.json")
    firmware_path = firmware_manifest_path.with_name(firmware_manifest_path.name[:-11] + ".hex")
    parameters = hardware_parameters(configuration)
    validate_firmware(firmware_path, firmware, parameters)
    build_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    build = root / "build" / "compiled" / build_id
    source = build / "source"
    source.mkdir(parents=True)
    inputs = sorted(path for path in (root / "rtl").glob("*.sv") if path.name != "rv32_board_top.sv")
    inputs += [root / "sim" / "coremark_compiled.cpp"]
    sources = {}
    for original in inputs:
        relative = original.relative_to(root)
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        sources[relative.as_posix()] = file_hash(destination)
    for filename in ("run_coremark_compiled.py", "check_coremark.py"):
        relative = Path("scripts") / filename
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
        sources[relative.as_posix()] = file_hash(destination)
    implementation_bound = validate_configuration_binding(configuration, firmware, sources)
    snapshot = build / "firmware.hex"
    shutil.copyfile(firmware_path, snapshot)
    validate_firmware(snapshot, firmware, parameters)
    if any(character in str(snapshot) for character in ('"', "\\", "\n", "\r")):
        raise ValueError("Firmware snapshot path cannot be a Verilog string literal")
    version = subprocess.check_output(["/usr/bin/verilator", "--version"], text=True).strip()
    object_directory = build / "objects"
    command = ["/usr/bin/verilator", "--cc", "--exe", "--build", "--Wall", "-Wno-fatal", "-j", "2",
               "--top-module", "rv32_soc", "--Mdir", str(object_directory),
               "-CFLAGS", "-O3 -std=c++14", "-GCLOCK_HZ=3200", "-GBAUD=100",
               '-GINIT_FILE="' + str(snapshot) + '"']
    command += [f"-G{name}={value}" for name, value in parameters.items()]
    command += [str(source / original.relative_to(root)) for original in inputs]
    manifest = {"SimulationBackend": version, "MeasurementKind": "rtl_simulation_not_hardware",
                "StartedUtc": datetime.now(timezone.utc).isoformat(), "BuildDirectory": str(build),
                "ConfigurationInput": configuration, "FirmwareBuild": firmware,
                "HardwareParameters": parameters, "FirmwareSha256": file_hash(snapshot),
                "SourceSnapshot": sources, "CompileCommand": command, "MaxCycles": max_cycles,
                "SimulationClockHz": 100000000, "UartModelClockHz": 3200,
                "ImplementationInputsBound": implementation_bound, "SimulationPassed": False}
    manifest_path = build / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled simulation directory: {build}", flush=True)
    with (build / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=build, check=True, stdout=log, stderr=subprocess.STDOUT)
    validate_compiler_warnings((build / "compile.log").read_text(encoding="utf-8"), source)
    executable = object_directory / "Vrv32_soc"
    manifest["ExecutableSha256"] = file_hash(executable)
    verify_artifacts(build, manifest)
    uart = build / "coremark.sim.uart"
    with (build / "simulation.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(executable), str(uart), str(max_cycles)], cwd=build, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    validate_firmware(snapshot, firmware, parameters)
    verify_artifacts(build, manifest)
    result = check_simulation_result(uart.read_text(encoding="ascii"), firmware, parameters, allow_short)
    (build / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    manifest["SimulationPassed"] = True
    manifest["CompletedUtc"] = datetime.now(timezone.utc).isoformat()
    manifest["UartSha256"] = file_hash(uart)
    manifest["ResultSha256"] = file_hash(build / "result.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("PASS compiled RTL simulation; not hardware evidence or an official CoreMark score.")
    return build


def main():
    parser = argparse.ArgumentParser(description="Compile and run actual SoC RTL; never hardware evidence")
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--firmware-manifest", type=Path, required=True)
    parser.add_argument("--max-cycles", type=int, default=50000000)
    parser.add_argument("--allow-short", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.max_cycles <= 1000000000000:
        parser.error("max-cycles must be in 1..1000000000000")
    try:
        execute(arguments.configuration.resolve(), arguments.firmware_manifest.resolve(),
                arguments.max_cycles, arguments.allow_short)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(f"FAIL compiled RTL simulation: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
