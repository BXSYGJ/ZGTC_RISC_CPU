"""Run source-bound, independent-service local RTL extraction miters."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

CLOSURE = ("rv32_core", "rv32_rvc_frontend", "rv32_rvc_expand", "rv32_decode",
           "rv32_alu", "rv32_muldiv", "rv32_btb", "rv32_machine")
RELEASES = ("Original_155250", "H3_Base_145125", "H3_Retained_145125")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def bound_file(path, expected):
    path = Path(path).resolve()
    if digest(path) != expected.lower():
        raise ValueError("Source SHA256 mismatch: " + str(path))
    return path


def linux(path):
    path = Path(path).resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", path):
        raise ValueError("Expected a Windows drive path")
    return "/mnt/" + path[0].lower() + "/" + path[3:]


def decode_process_output(data):
    # The Windows WSL launcher can prepend a localized UTF-16LE diagnostic to
    # the Linux program's UTF-8 stream. Preserve bytes and decode each segment.
    parts = []
    while data:
        head = data[:64]
        utf16 = data.startswith(b"\xff\xfe") or (len(head) > 5 and head[1::2].count(0) > len(head[1::2]) // 3)
        if utf16:
            marker = data.find(b"\r\x00\n\x00")
            end = marker + 4 if marker >= 0 else len(data)
            parts.append(data[:end].decode("utf-16", errors="replace") if data.startswith(b"\xff\xfe") else
                         data[:end].decode("utf-16-le", errors="replace"))
            data = data[end:]
        else:
            parts.append(data.decode("utf-8-sig", errors="replace"))
            break
    return "".join(parts)


def execute(arguments, prefix, *, expect=0, timeout=900):
    prefix = Path(prefix)
    start = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(["wsl.exe"] + arguments, capture_output=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    Path(str(prefix) + ".stdout.raw").write_bytes(result.stdout)
    Path(str(prefix) + ".stderr.raw").write_bytes(result.stderr)
    stdout, stderr = decode_process_output(result.stdout), decode_process_output(result.stderr)
    Path(str(prefix) + ".stdout.log").write_text(stdout, encoding="utf-8")
    Path(str(prefix) + ".stderr.log").write_text(stderr, encoding="utf-8")
    receipt = {"executable": "wsl.exe", "arguments": arguments, "exit_code": result.returncode,
               "started_utc": start, "finished_utc": datetime.now(timezone.utc).isoformat(),
               "stdout": str(prefix) + ".stdout.log", "stderr": str(prefix) + ".stderr.log",
               "stdout_raw": str(prefix) + ".stdout.raw", "stderr_raw": str(prefix) + ".stderr.raw"}
    write_json(str(prefix) + ".command.json", receipt)
    if result.returncode != expect:
        raise ValueError(f"Process {prefix.name} returned {result.returncode}, expected {expect}; inspect its logs")
    return receipt, stdout, stderr


def parse_ports(text):
    header = text.split(");", 1)[0]
    ports = []
    for match in re.finditer(r"^\s*(input|output)\s+wire\s+(?:\[(\d+):(\d+)\]\s+)?([^\r\n]+)", header, re.M):
        width = int(match[2]) - int(match[3]) + 1 if match[2] else 1
        for name in match[4].rstrip(",").split(","):
            name = name.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", name):
                raise ValueError("Unexpected core interface syntax: " + name)
            ports.append({"name": name, "direction": match[1], "width": width})
    return ports


def rename_reference(text):
    for module in sorted(CLOSURE, key=len, reverse=True):
        text = re.sub(r"\b" + module + r"\b", "reference_" + module, text)
    return text


def create_top(ports, native):
    selected = [port for port in ports if port["name"] not in ("clk", "rst_n")]
    groups = ["core." + port["name"] for port in selected]
    groups += ["serial_tx", "gpio_output", "status_code", "maintenance_fault", "mmio_req_valid",
               "mmio_req_ready", "mmio_rsp_valid", "mmio_rsp_ready", "mmio_rsp_data", "mmio_rsp_error"]
    if len(groups) > 64:
        raise ValueError("Miter mismatch mask exceeds 64 independent groups")
    width = sum(port["width"] for port in selected)
    parameters = ".ENABLE_M(1),.ENABLE_C(1),.ENABLE_PREDICTOR(1),.LOAD_USE_BUBBLE(1)," + \
                 ".FAST_ICACHE_HIT(1),.FAST_DCACHE_READ(1),.FAST_DCACHE_WRITE(1)," + \
                 ".FETCH_OVERLAP(1),.DATA_OVERLAP(1),.EARLY_D_REQUEST(1)," + \
                 ".BTB_INDEX_BITS(8),.ICACHE_SET_BITS(9),.CACHE_SET_BITS(6)," + \
                 ".ENABLE_CACHE(1),.MEMORY_ADDRESS_BITS(14),.CLOCK_HZ(3200),.BAUD(100),.INIT_FILE(\"firmware.hex\")"
    lines = ["`timescale 1ns/1ps", "module bare_extraction_miter (",
             " input wire clk,rst_n,serial_rx,inject_bus_fault,", " input wire [7:0] gpio_input,",
             " output wire [63:0] mismatch,", f" output wire [{width - 1}:0] reference_frame,bare_frame,",
             " output wire serial_tx,maintenance_fault,trap_valid,trace_valid,trace_write,",
             " output wire i_request_fire,i_response_fire,d_request_fire,d_response_fire,maintenance_fire,",
             " output wire [31:0] status_code,trace_pc,", " output wire [63:0] cycle_count,retired_count", ");"]
    if native:
        lines += [" GTP_GRS GRS_INST(.GRS_N(1'b1));"]
    for name, module in (("reference_soc", "reference_soc"), ("environment", "bare_environment")):
        extra = ".inject_bus_fault(inject_bus_fault)," if name == "environment" else ""
        lines += [f" {module} #({parameters}) {name}(",
                  "  " + extra + ".clk(clk),.rst_n(rst_n),.serial_rx(serial_rx),.gpio_input(gpio_input),",
                  "  .serial_tx(),.gpio_output(),.status_code(),.maintenance_fault(),",
                  "  .trace_valid(),.trace_pc(),.trace_instruction(),.trap_valid(),.trap_cause(),",
                  "  .cycle_count(),.retired_count());"]
    for index, name in enumerate(groups):
        lines += [f" assign mismatch[{index}]=(reference_soc.{name} !== environment.{name});"]
    if len(groups) < 64:
        lines += [f" assign mismatch[63:{len(groups)}]=0;"]
    for output, instance in (("reference_frame", "reference_soc"), ("bare_frame", "environment")):
        lines += [" assign " + output + "={" + ",".join(instance + ".core." + port["name"] for port in selected) + "};"]
    for name in ("serial_tx", "maintenance_fault", "status_code"):
        lines += [f" assign {name}=environment.{name};"]
    for name in ("trap_valid", "trace_valid", "trace_write", "trace_pc", "cycle_count", "retired_count"):
        lines += [f" assign {name}=environment.core.{name};"]
    lines += [" assign i_request_fire=environment.i_req_valid && environment.i_req_ready;",
              " assign i_response_fire=environment.i_rsp_valid && environment.i_rsp_ready;",
              " assign d_request_fire=environment.d_req_valid && environment.d_req_ready;",
              " assign d_response_fire=environment.d_rsp_valid && environment.d_rsp_ready;",
              " assign maintenance_fire=environment.maintenance_valid && environment.maintenance_ready;", "endmodule", ""]
    return "\n".join(lines), width, groups


def prepare(root, release):
    manifest_path = root / release / "SOURCE_MANIFEST.json"
    manifest = read_json(manifest_path)
    if manifest["release"] != release or manifest["functional_rtl_changes"] != 0:
        raise ValueError("Expected unchanged bare-core source identity")
    if set(item["name"] for item in manifest["rtl"]) != {module + ".sv" for module in CLOSURE}:
        raise ValueError("Pure core source closure differs from its exact eight modules")
    parent_path = bound_file(manifest["source_waveform_manifest"], manifest["source_waveform_manifest_sha256"])
    parent = read_json(parent_path)
    waveform_run = Path(parent["simulation_run_directory"])
    parent_compile = read_json(waveform_run / "compile.command.json")
    native = release != "Original_155250"
    source_wrapper = bound_file(manifest["wrapper"]["path"], manifest["wrapper"]["sha256"])
    source_inputs = {Path(item["path"]).name: bound_file(item["path"], item["sha256"]) for item in parent["source_inputs"]}
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run = root / "analysis" / "extraction" / release / tag
    inputs = run / "inputs"
    for directory in ("bare", "reference", "environment", "vendor"):
        (inputs / directory).mkdir(parents=True, exist_ok=True)
    audit = []
    for item in manifest["rtl"]:
        bare = bound_file(item["path"], item["sha256"])
        original = bound_file(item["source"], item["sha256"])
        if original != source_inputs[item["name"]]:
            raise ValueError("Bare extraction source differs from the established simulation source")
        shutil.copyfile(bare, inputs / "bare" / item["name"])
        renamed = rename_reference(original.read_text(encoding="utf-8-sig"))
        (inputs / "reference" / item["name"]).write_text(renamed, encoding="utf-8")
        audit.append({"name": item["name"], "bare": str(bare), "reference_original": str(original),
                      "sha256": item["sha256"], "exact_bytes_equal": bare.read_bytes() == original.read_bytes(),
                      "reference_transform": "Only module-type identifiers gain reference_ prefix"})
    shutil.copyfile(source_wrapper, inputs / "bare" / source_wrapper.name)
    ports = parse_ports(source_inputs["rv32_core.sv"].read_text(encoding="utf-8-sig"))
    if ports != parse_ports(source_wrapper.read_text(encoding="utf-8-sig")):
        raise ValueError("Bare wrapper does not expose the complete exact core interface")
    core_text = source_inputs["rv32_core.sv"].read_text(encoding="utf-8-sig")
    expected = {"RESET_VECTOR": 0, "ENABLE_PREDICTOR": 1, "ENABLE_M": 1, "ENABLE_C": 1,
                "FETCH_ADDRESS_BITS": 16, "FETCH_OVERLAP": 1, "EARLY_D_REQUEST": 1,
                "BTB_INDEX_BITS": 8, "BTB_ADDRESS_BITS": 16, "LOAD_USE_BUBBLE": 1}
    if "RETAIN_MUL_ELIGIBILITY" in core_text:
        expected["RETAIN_MUL_ELIGIBILITY"] = 1
    if manifest["parameters"] != expected:
        raise ValueError("Bare parameters differ from the parent core configuration")
    wrapper_text = source_wrapper.read_text(encoding="utf-8-sig")
    for name, value in expected.items():
        if not re.search(r"\." + name + r"\(" + str(value) + r"\)", wrapper_text):
            raise ValueError("Wrapper parameter binding differs: " + name)
    soc = source_inputs["rv32_soc.sv"].read_text(encoding="utf-8-sig")
    reference = rename_reference(soc).replace("module rv32_soc", "module reference_soc", 1)
    (inputs / "reference" / "reference_soc.sv").write_text(reference, encoding="utf-8")
    environment = soc.replace("module rv32_soc", "module bare_environment", 1)
    environment = environment.replace("    input wire clk,", "    input wire inject_bus_fault,\n    input wire clk,", 1)
    environment, count = re.subn(r"rv32_core\s*#\([\s\S]*?\)\s*core\s*\(", "rv32_bare_core core(", environment, count=1)
    if count != 1:
        raise ValueError("Original SoC core-instance replacement is ambiguous")
    anchor = ".d_rsp_data(d_rsp_data),.d_rsp_error(d_rsp_error)"
    if environment.count(anchor) < 1:
        raise ValueError("Fault-control attachment point missing")
    environment = environment.replace(anchor, ".d_rsp_data(d_rsp_data ^ {32{inject_bus_fault}}),.d_rsp_error(d_rsp_error)", 1)
    (inputs / "environment" / "bare_environment.sv").write_text(environment, encoding="utf-8")
    compiled_rtl = []
    for argument in parent_compile["arguments"]:
        if "/inputs/rtl/" in argument and argument.endswith(".sv"):
            name = argument.rsplit("/", 1)[1]
            if name not in {module + ".sv" for module in CLOSURE} | {"rv32_soc.sv"}:
                path = source_inputs[name]
                shutil.copyfile(path, inputs / "environment" / name)
                compiled_rtl.append(inputs / "environment" / name)
    if native:
        for name in ("GTP_DRM36K_E1.v", "GTP_GRS.v"):
            shutil.copyfile(waveform_run / "inputs" / "sim" / "vendor" / name, inputs / "vendor" / name)
        shutil.copyfile(waveform_run / "inputs" / "sim" / "native_timing_tick_v2.h", inputs / "native_timing_tick_v2.h")
    firmware = bound_file(waveform_run / "firmware.hex", parent["firmware_sha256"])
    shutil.copyfile(firmware, run / "firmware.hex")
    template = Path(__file__).with_name("extraction_driver.cpp")
    shutil.copyfile(template, inputs / "driver.cpp")
    top, frame_width, groups = create_top(ports, native)
    top_path = inputs / "bare_extraction_miter.sv"
    top_path.write_text(top, encoding="utf-8")
    # The service has two independent instances of each actual memory/peripheral
    # module. They are never part of the eight-file DUT synthesis closure.
    sources = (sorted((inputs / "bare").glob("*.sv")) + sorted((inputs / "reference").glob("*.sv"))
               + sorted((inputs / "environment").glob("*.sv")) + sorted((inputs / "vendor").glob("*.v")) + [top_path])
    tool = parent_compile["arguments"][3]
    flags = ["--cc", "--exe", "--build"] + (["--timing"] if native else [])
    cflags = ("-O3 -std=c++20" if native else "-O3 -std=c++14")
    cflags += f" -DMITER_NATIVE={int(native)} -DMITER_FRAME_BITS={frame_width} -DMITER_FRAME_WORDS={(frame_width + 31) // 32}"
    arguments = ["--cd", "/tmp", "--exec", tool] + flags + ["--Wall", "-Wno-fatal", "-j", "1", "-MAKEFLAGS", "OPT_FAST=-O3",
                 "--top-module", "bare_extraction_miter", "--Mdir", linux(run / "objects"), "-CFLAGS", cflags]
    arguments += [linux(path) for path in sources] + [linux(inputs / "driver.cpp")]
    receipt = {"schema": 1, "release": release, "origin": "LOCAL RTL SIMULATION",
               "bare_source_manifest": str(manifest_path), "bare_source_manifest_sha256": digest(manifest_path),
               "parent_waveform_manifest": str(parent_path), "parent_waveform_manifest_sha256": digest(parent_path),
               "core_closure": audit, "parameters": expected, "ports": ports, "frame_bits": frame_width,
               "mismatch_groups": groups, "wrapper": str(source_wrapper), "wrapper_sha256": digest(source_wrapper),
               "configured_core_clock_hz": manifest["configured_clock_hz"], "simulation_clock_hz": 3200, "uart_baud": 100,
               "external_service": {"kind": "Unmodified selected rv32_memory_system and rv32_peripherals outside DUT",
                   "cache_enabled": True, "i_cache_set_bits": 9, "d_cache_set_bits": 6, "ram_bytes": 65536,
                   "two_independent_service_instances": True, "native_vendor_memory_model": native,
                   "excluded_from_dut_synthesis": True},
               "firmware_sha256": digest(firmware), "tool": tool, "compile_arguments": arguments,
               "miter_driver_template_sha256": digest(template), "generator_sha256": digest(__file__),
               "inputs": [{"path": str(path), "sha256": digest(path)} for path in sorted(inputs.rglob("*")) if path.is_file()]}
    write_json(run / "PREPARATION.json", receipt)
    return run, receipt


def qualify(root, release, cycles):
    run, prepared = prepare(root, release)
    print(json.dumps({"state": "COMPILING", "release": release, "run": str(run)}), flush=True)
    execute(prepared["compile_arguments"], run / "compile", timeout=900)
    executable = run / "objects" / "Vbare_extraction_miter"
    baseline, stdout, _ = execute(["--cd", linux(run), "--exec", linux(executable), linux(run / "baseline.json"), str(cycles), "0"], run / "baseline", timeout=180)
    baseline_data = read_json(run / "baseline.json")
    negative, _, negative_error = execute(["--cd", linux(run), "--exec", linux(executable), linux(run / "rejected.json"), str(cycles), "10000"], run / "modified-negative-control", expect=1, timeout=30)
    if "EXTRACTION_MISMATCH edge=10000 phase=preedge" not in negative_error:
        raise ValueError("Controlled DUT input fault did not fail at the intended first observation")
    rollback, _, _ = execute(["--cd", linux(run), "--exec", linux(executable), linux(run / "rollback.json"), str(cycles), "0"], run / "rollback", timeout=180)
    if baseline_data != read_json(run / "rollback.json"):
        raise ValueError("Restored independent execution differs from the baseline")
    for item in prepared["inputs"]:
        bound_file(item["path"], item["sha256"])
    bound_file(prepared["wrapper"], prepared["wrapper_sha256"])
    bound_file(prepared["bare_source_manifest"], prepared["bare_source_manifest_sha256"])
    result = {"schema": 1, "status": "PASS", "release": release, "origin": "LOCAL RTL SIMULATION",
              "scope": "Fresh finite extraction miter; exact core wrapper versus independent original SoC with external cached-system service",
              "full_coremark_run": False, "hardware_measurement": False, "standalone_cacheless_memory_service_score": False,
              "area_efficiency_denominator": "Core-only implementation area with explicitly external cached-system services",
              "preparation": str(run / "PREPARATION.json"), "preparation_sha256": digest(run / "PREPARATION.json"),
              "baseline": baseline, "modified_negative_control": negative, "rollback": rollback,
              "result": baseline_data, "controlled_fault": "XOR32 into only bare DUT d_rsp_data input at edge10000; environment and reference unchanged",
              "restored_behavior_equal": True, "simulator_executable": str(executable), "simulator_executable_sha256": digest(executable),
              "raw_result_sha256": digest(run / "baseline.json"), "rollback_result_sha256": digest(run / "rollback.json"),
              "uart_sha256": digest(run / "uart.log"), "completed_utc": datetime.now(timezone.utc).isoformat()}
    write_json(run / "QUALIFICATION.json", result)
    final = root / "analysis" / (release + "-EXTRACTION_QUALIFICATION.json")
    write_json(final, result)
    if read_json(final) != result or read_json(run / "QUALIFICATION.json") != result:
        raise ValueError("Qualification receipt failed reopening verification")
    print(stdout.strip(), flush=True)
    print(json.dumps({"state": "PASS", "release": release, "receipt": str(final)}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--release", choices=RELEASES, action="append")
    parser.add_argument("--cycles", type=int, default=2000000)
    args = parser.parse_args()
    try:
        if not 2000000 <= args.cycles <= 10000000:
            raise ValueError("The strong short qualification needs 2M to 10M CPU edges")
        for release in args.release or RELEASES:
            qualify(args.root.resolve(), release, args.cycles)
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"state": "FAILED", "error": str(error)}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
