import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[1] / "scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from load_use_profile import DRIVER_SHA256, extract_cycle_pc, file_hash, firmware_image, load_json, require
from run_load_use_profile import verified_build
from run_coremark_compiled import check_simulation_result, validate_compiler_warnings

SHORT = ROOT / "build/compiled/20260910-233631-e15b5716"
REFERENCE = ROOT / "build/execution-profile-current"
OUTPUT = ROOT / "build/control-events-current"
FLAGS = (
    "ex_valid", "ex_fire", "mem_valid", "mem_fire", "wb_valid", "id_valid", "id_fire", "if_valid", "if_fire",
    "mem_ready", "mem_flush", "ex_redirect", "frontend_flush", "load_use_wait", "early_load_dependency",
    "ex_serial", "ex_muldiv", "muldiv_valid", "ex_decode.is_branch", "ex_decode.is_jal", "ex_decode.is_jalr",
    "mem_branch", "mem_conditional", "mem_early_redirect", "frontend_barrier", "fetch_redirect_pending",
    "i_req_valid", "i_req_ready", "i_rsp_valid", "i_rsp_ready", "ex_can_fire", "interrupt_pending",
)


def replace_once(text, before, after):
    require(text.count(before) == 1, "Observer anchor missing or ambiguous")
    return text.replace(before, after)


def observe_soc(text):
    text = replace_once(text, "    output wire [63:0] retired_count\n", "    output wire [63:0] retired_count,\n    output wire [31:0] control_flags,control_ex_pc,control_mem_pc\n")
    assignments = "    assign control_flags={" + ",".join("core." + name for name in reversed(FLAGS)) + "};\n"
    assignments += "    assign control_ex_pc=core.ex_pc;\n    assign control_mem_pc=core.mem_pc;\n"
    return replace_once(text, "endmodule", assignments + "endmodule")


def observe_driver(text):
    setup = '        std::ofstream control_trace(std::string(argv[1]) + ".control.bin", std::ios::binary);\n'
    setup += '        if (!control_trace) throw std::runtime_error("Cannot open control trace");\n'
    text = replace_once(text, "        bool trace_started = false;", setup + "        bool trace_started = false;")
    lines = [
        "            if (trace_started && !trace_finished) {",
        "                char control_record[20];",
        "                const uint64_t timestamp = model->cycle_count;",
        "                const uint32_t values[3] = {model->control_ex_pc, model->control_mem_pc, model->control_flags};",
        "                for (unsigned byte_index = 0; byte_index < 8; ++byte_index)",
        "                    control_record[byte_index] = static_cast<char>(timestamp >> (byte_index * 8));",
        "                for (unsigned field = 0; field < 3; ++field)",
        "                    for (unsigned byte_index = 0; byte_index < 4; ++byte_index)",
        "                        control_record[8 + field * 4 + byte_index] = static_cast<char>(values[field] >> (byte_index * 8));",
        "                control_trace.write(control_record, sizeof(control_record));",
        "            }",
    ]
    text = replace_once(text, "            tick();\n            if (model->trace_valid)", "\n".join(lines) + "\n            tick();\n            if (model->trace_valid)")
    return replace_once(text, "                retirement_trace.flush();", '                control_trace.flush();\n                if (!control_trace) throw std::runtime_error("Control trace write failed");\n                retirement_trace.flush();')


def run(command, log, environment=None):
    completed = subprocess.run(list(map(str, command)), capture_output=True, text=True, env=environment, timeout=300)
    log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    require(completed.returncode == 0, "Control observation command failed: " + str(log))
    return completed.stdout + completed.stderr


def main():
    from audit_clock import audit_sources
    audit_sources()
    manifest, result = verified_build(SHORT)
    for relative, expected in manifest["SourceSnapshot"].items():
        require(file_hash(ROOT / relative) == expected, "Current source changed: " + relative)
    observer = ROOT.parents[1] / "build/load-use-profile-stage/sim/coremark_compiled.cpp"
    require(file_hash(observer) == DRIVER_SHA256, "Original retirement observer changed")
    reference = load_json(REFERENCE / "results.json")
    for field, filename in (("trace_sha256", "uart.log.retire.bin"), ("trace_metadata_sha256", "uart.log.retire.json")):
        require(file_hash(REFERENCE / filename) == reference[field], "Reference retirement artifact changed")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    shutil.copytree(SHORT / "source", OUTPUT / "source")
    shutil.copyfile(SHORT / "firmware.hex", OUTPUT / "firmware.hex")
    shutil.copyfile(Path(__file__), OUTPUT / "generator-original.py")
    (OUTPUT / "source/rtl/rv32_soc.sv").write_text(observe_soc((SHORT / "source/rtl/rv32_soc.sv").read_text()), encoding="utf-8")
    (OUTPUT / "source/sim/coremark_compiled.cpp").write_text(observe_driver(observer.read_text()), encoding="utf-8")
    image = firmware_image(OUTPUT / "firmware.hex")
    firmware = manifest["FirmwareBuild"]
    elf = (ROOT.parent / "full_mul_precompute_clock154285/build" / firmware["RunName"]).with_suffix(".elf")
    prefix = firmware["Toolchain"]["Prefix"]
    run([prefix + "objcopy", "-O", "binary", elf, OUTPUT / "firmware.bin"], OUTPUT / "objcopy.log")
    binary = (OUTPUT / "firmware.bin").read_bytes()
    require(len(binary) <= len(image) and binary.ljust(len(image), b"\0") == image, "ELF differs from firmware")
    boundaries = {}
    for function in ("start_time", "stop_time"):
        text = run([prefix + "objdump", "-d", "--disassemble=" + function, elf], OUTPUT / (function + ".txt"))
        boundaries[function] = extract_cycle_pc(text, image, function)
    command = [argument.replace(str(SHORT), str(OUTPUT)) for argument in manifest["CompileCommand"]]
    inputs = {relative: file_hash(OUTPUT / "source" / relative) for relative in manifest["SourceSnapshot"]}
    record = {"schema": 1, "scope": "simulation-only internal events before each clock edge; no synthesized hardware changes",
              "flags": FLAGS, "record_bytes": 20, "record_layout": "little-endian QIII: cycle, ex_pc, mem_pc, flags",
              "inputs": inputs, "baseline_manifest_sha256": file_hash(SHORT / "manifest.json"), "boundaries": boundaries,
              "firmware_sha256": file_hash(OUTPUT / "firmware.hex"), "elf_sha256": file_hash(elf),
              "compile_command": command, "runner_sha256": file_hash(Path(__file__)), "passed": False}
    (OUTPUT / "invocation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    text = run(command, OUTPUT / "compile.log")
    validate_compiler_warnings(text, OUTPUT / "source")
    environment = os.environ.copy()
    environment.update(ZGTC_TRACE_START_PC=f"{boundaries['start_time']:x}", ZGTC_TRACE_STOP_PC=f"{boundaries['stop_time']:x}")
    run([OUTPUT / "objects/Vrv32_soc", OUTPUT / "uart.log", "10000000"], OUTPUT / "execute.log", environment)
    require((OUTPUT / "uart.log").read_bytes() == (SHORT / "coremark.sim.uart").read_bytes(), "Observation changed UART")
    measured = check_simulation_result((OUTPUT / "uart.log").read_text(), firmware, manifest["HardwareParameters"], True)
    require(measured == result, "Observation changed complete short result")
    for filename in ("uart.log.retire.bin", "uart.log.retire.json"):
        require(file_hash(OUTPUT / filename) == file_hash(REFERENCE / filename), "Observation changed exact retirement trace")
    metadata = load_json(OUTPUT / "uart.log.retire.json")
    require((OUTPUT / "uart.log.control.bin").stat().st_size == 20 * metadata["cycles"], "Control trace does not cover every timed cycle")
    record.update(passed=True, result=result, metadata=metadata,
                  outputs={name: file_hash(OUTPUT / name) for name in ("objects/Vrv32_soc", "uart.log", "uart.log.retire.bin", "uart.log.retire.json", "uart.log.control.bin", "compile.log", "execute.log")})
    (OUTPUT / "invocation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "cycles": metadata["cycles"], "output": str(OUTPUT), "unchanged_retirement_trace": True}, indent=2))


if __name__ == "__main__":
    main()
