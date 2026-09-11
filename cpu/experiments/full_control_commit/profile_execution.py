import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from load_use_profile import DRIVER_SHA256, extract_cycle_pc, file_hash, firmware_image, load_json, require, trace_records
from run_load_use_profile import verified_build
from run_coremark_compiled import validate_compiler_warnings, check_simulation_result

SHORT = ROOT / "build/compiled/20260910-195856-6bf511dd"
OUTPUT = ROOT / "build/execution-profile-current"


def run(command, log, environment=None):
    completed = subprocess.run(list(map(str, command)), capture_output=True, text=True, env=environment, timeout=300)
    log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    require(completed.returncode == 0, "Command failed: " + str(log))
    return completed.stdout + completed.stderr


def main():
    manifest, baseline_result = verified_build(SHORT)
    for relative, expected in manifest["SourceSnapshot"].items():
        require(file_hash(ROOT / relative) == expected, "Current source changed: " + relative)
    observer = ROOT.parents[1] / "build/load-use-profile-stage/sim/coremark_compiled.cpp"
    require(file_hash(observer) == DRIVER_SHA256, "Unexpected retirement observer")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SHORT / "source", OUTPUT / "source")
    shutil.copyfile(observer, OUTPUT / "source/sim/coremark_compiled.cpp")
    shutil.copyfile(SHORT / "firmware.hex", OUTPUT / "firmware.hex")
    image = firmware_image(OUTPUT / "firmware.hex")
    firmware = manifest["FirmwareBuild"]
    stem = ROOT.parent / "full_mul_precompute_clock154285/build" / firmware["RunName"]
    elf = stem.with_suffix(".elf")
    prefix = firmware["Toolchain"]["Prefix"]
    run([prefix + "objcopy", "-O", "binary", elf, OUTPUT / "firmware.bin"], OUTPUT / "objcopy.log")
    binary = (OUTPUT / "firmware.bin").read_bytes()
    require(len(binary) <= len(image) and binary.ljust(len(image), b"\0") == image, "ELF and firmware differ")
    boundaries = {}
    for function in ("start_time", "stop_time"):
        text = run([prefix + "objdump", "-d", "--disassemble=" + function, elf], OUTPUT / (function + ".txt"))
        boundaries[function] = extract_cycle_pc(text, image, function)
    command = [argument.replace(str(SHORT), str(OUTPUT)) for argument in manifest["CompileCommand"]]
    inputs = {relative: file_hash(OUTPUT / "source" / relative) for relative in manifest["SourceSnapshot"]}
    require(inputs == dict(manifest["SourceSnapshot"], **{"sim/coremark_compiled.cpp": DRIVER_SHA256}), "Observer modified RTL")
    invocation = {"scope": "timer-bounded RTL retirement observation, not hardware", "inputs": inputs,
                  "baseline_manifest_sha256": file_hash(SHORT / "manifest.json"), "compile_command": command,
                  "firmware_sha256": file_hash(OUTPUT / "firmware.hex"), "elf_sha256": file_hash(elf),
                  "boundaries": boundaries, "runner_sha256": file_hash(Path(__file__)), "passed": False}
    (OUTPUT / "invocation.json").write_text(json.dumps(invocation, indent=2) + "\n", encoding="utf-8")
    compile_text = run(command, OUTPUT / "compile.log")
    validate_compiler_warnings(compile_text, OUTPUT / "source")
    environment = os.environ.copy()
    environment.update(ZGTC_TRACE_START_PC=f"{boundaries['start_time']:x}", ZGTC_TRACE_STOP_PC=f"{boundaries['stop_time']:x}")
    run([OUTPUT / "objects/Vrv32_soc", OUTPUT / "uart.log", "10000000"], OUTPUT / "execute.log", environment)
    require((OUTPUT / "uart.log").read_bytes() == (SHORT / "coremark.sim.uart").read_bytes(), "Observation changed UART")
    result = check_simulation_result((OUTPUT / "uart.log").read_text(), firmware, manifest["HardwareParameters"], True)
    require(result == baseline_result, "Observation changed full CoreMark result")
    metadata = load_json(OUTPUT / "uart.log.retire.json")
    require(metadata["start_pc"] == boundaries["start_time"] and metadata["stop_pc"] == boundaries["stop_time"], "Wrong timer boundaries")
    require(metadata["cycles"] == result["cycles"], "Trace interval differs from scored interval")
    operations = Counter()
    gaps = Counter()
    excess = Counter()
    multiply_pcs = Counter()
    previous = None
    records = 0
    for cycle, address, instruction in trace_records(OUTPUT / "uart.log.retire.bin", metadata, image):
        opcode = instruction & 127
        funct3 = (instruction >> 12) & 7
        operation = ("MUL", "MULH", "MULHSU", "MULHU", "DIV", "DIVU", "REM", "REMU")[funct3] if opcode == 0x33 and instruction >> 25 == 1 else f"opcode_{opcode:02x}"
        operations[operation] += 1
        if operation in ("MUL", "MULH", "MULHSU", "MULHU"):
            multiply_pcs[f"{address:08x}:{operation}"] += 1
        if previous is not None:
            interval = cycle - previous
            gaps[f"{operation}:{interval}"] += 1
            excess[operation] += interval - 1
        previous = cycle
        records += 1
    require(records == metadata["records"], "Trace record count mismatch")
    report = {"scope": "timed RTL retirement intervals; interval grouping is not internal stall causality",
              "records": records, "metadata": metadata, "operations": dict(operations), "gap_histogram": dict(gaps),
              "excess_retirement_cycles_by_next_operation": dict(excess), "multiply_pcs": dict(multiply_pcs),
              "result": result, "passed": True, "hardware_validated": False,
              "invocation_sha256": file_hash(OUTPUT / "invocation.json"),
              "trace_sha256": file_hash(OUTPUT / "uart.log.retire.bin"), "trace_metadata_sha256": file_hash(OUTPUT / "uart.log.retire.json"),
              "executable_sha256": file_hash(OUTPUT / "objects/Vrv32_soc"), "uart_sha256": file_hash(OUTPUT / "uart.log")}
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
