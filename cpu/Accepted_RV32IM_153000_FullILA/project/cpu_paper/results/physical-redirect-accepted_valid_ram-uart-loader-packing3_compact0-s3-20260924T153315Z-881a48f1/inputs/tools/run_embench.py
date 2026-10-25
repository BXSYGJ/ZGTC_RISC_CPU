"""Build pinned, unchanged Embench workloads and execute the reference RTL.

Invoke through PowerShell -> wsl --exec python3. No shell command composition.
All generated material is isolated under cpu_paper/results in unique runs.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "cpu/experiments/full_fetch_commit_factored"
PORT = ROOT / "ports/embench"
UPSTREAM = ROOT / "third_party/embench-iot"
TOOL = ROOT / "tools/xpack-riscv-none-embed-gcc-10.2.0-1.2/bin/riscv-none-embed-"
FLAGS = ["-march=rv32im", "-mabi=ilp32", "-mcmodel=medany", "-msmall-data-limit=0",
         "-std=c11", "-O3", "-funroll-loops", "-ffreestanding", "-fno-builtin",
         "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra"]
PARAMS = {"ENABLE_M": 1, "ENABLE_PREDICTOR": 1, "LOAD_USE_BUBBLE": 1,
          "FAST_ICACHE_HIT": 1, "FAST_DCACHE_READ": 1, "FAST_DCACHE_WRITE": 1,
          "FETCH_OVERLAP": 1, "DATA_OVERLAP": 1, "EARLY_D_REQUEST": 1,
          "BTB_INDEX_BITS": 8, "ICACHE_SET_BITS": 9, "CACHE_SET_BITS": 6,
          "ENABLE_CACHE": 1, "MEMORY_ADDRESS_BITS": 14}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def command(args, cwd, name, timeout=300):
    args = list(map(str, args))
    write_json(cwd / (name + ".command.json"), {"argv": args, "cwd": str(cwd), "timeout_seconds": timeout})
    with (cwd / (name + ".log")).open("w", encoding="utf-8") as log:
        try:
            completed = subprocess.run(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            return completed.returncode
        except subprocess.TimeoutExpired:
            log.write("\nTIMEOUT\n")
            return 124


def snapshot(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if sha(source) != sha(target):
        raise ValueError("Snapshot differs from input")


def source_snapshot(run):
    lock = json.loads((ROOT / "third_party/SOURCES_LOCK.json").read_text(encoding="utf-8-sig"))
    repo = next(r for r in lock["repositories"] if r["path"] == "embench-iot")
    for name, expected in repo["sha256"].items():
        source = UPSTREAM / name
        if sha(source) != expected:
            raise ValueError("Pinned Embench source changed: " + name)
        snapshot(source, run / "inputs/embench" / name)
    for source in PORT.iterdir():
        if source.is_file():
            snapshot(source, run / "inputs/port" / source.name)
    for name in ("start.S", "link_soc.ld"):
        snapshot(REFERENCE / "sw" / name, run / "inputs/port" / name)
    linker = run / "inputs/port/link_soc.ld"
    original_linker = linker.read_bytes()
    if original_linker.count(b"__stack_top - 4096") != 1:
        raise ValueError("Unexpected reference linker stack reservation")
    snapshot(REFERENCE / "sw/link_soc.ld", run / "inputs/reference_link_soc.ld")
    linker.write_bytes(original_linker.replace(b"__stack_top - 4096", b"__stack_top - 16384"))
    for source in sorted((REFERENCE / "rtl").glob("*.sv")):
        snapshot(source, run / "inputs/rtl" / source.name)
    snapshot(REFERENCE / "configuration.json", run / "inputs/configuration.json")
    for name in ("protocol_v1.md", "protocol_v2.md", "protocol_v3.md"):
        snapshot(ROOT / name, run / "inputs" / name)
    snapshot(Path(__file__), run / "inputs/run_embench.py")
    inputs = {p.relative_to(run / "inputs").as_posix(): sha(p)
              for p in sorted((run / "inputs").rglob("*")) if p.is_file()}
    write_json(run / "source-hashes.json", inputs)
    return lock, inputs


def build_simulator(run):
    build = run / "simulator"
    build.mkdir()
    sources = [p for p in sorted((run / "inputs/rtl").glob("*.sv")) if p.name != "rv32_board_top.sv"]
    args = ["/usr/bin/verilator", "--cc", "--exe", "--build", "--Wall", "-Wno-fatal", "-j", "4",
            "--top-module", "rv32_observed_soc", "--Mdir", build / "objects", "-CFLAGS", "-O3 -std=c++14",
            "-GCLOCK_HZ=3200", "-GBAUD=100", '-GINIT_FILE="firmware.hex"']
    args += [f"-G{k}={v}" for k, v in PARAMS.items()]
    args += sources + [run / "inputs/port/rv32_observed_soc.sv", run / "inputs/port/sim_main.cpp"]
    code = command(args, build, "compile", 900)
    if code:
        raise RuntimeError("RTL compile failed; inspect " + str(build / "compile.log"))
    text = (build / "compile.log").read_text(encoding="utf-8")
    warnings = re.findall(r"^%Warning[^\n]*", text, flags=re.MULTILINE)
    unexpected = [w for w in warnings if not (w.startswith("%Warning-WIDTH:") and "rv32_burst_ram.sv:" in w and "Operator NEQ" in w)]
    write_json(build / "warnings.json", {"warnings": warnings, "unexpected": unexpected})
    if unexpected:
        raise RuntimeError("Unreviewed Verilator warning")
    return build / "objects/Vrv32_observed_soc"


def build_workload(run, name, args):
    work = run / "workloads" / name
    work.mkdir(parents=True)
    base = run / "inputs"
    port = base / "port"
    embench = base / "embench"
    workload_directory = embench / ("support/dummy-benchmark" if name == "instrumentation-dummy" else "src/" + name)
    sources = sorted(workload_directory.glob("*.c"))
    if not sources:
        raise ValueError("No workload sources: " + name)
    sources += [embench / "support/beebsc.c", port / "main.c", port / "boardsupport.c", port / "syscalls.c", port / "start.S"]
    elf = work / "firmware.elf"
    compile_args = [str(TOOL) + "gcc"] + FLAGS + [f"-DWARMUP_HEAT={args.warmup}", f"-DGLOBAL_SCALE_FACTOR={args.scale}",
        "-I", port, "-I", embench / "support", "-I", workload_directory,
        "-nostdlib", "-nostartfiles", "-Wl,--relax", "-Wl,--gc-sections", "-Wl,-Map=firmware.map",
        "-T", port / "link_soc.ld", "-o", elf] + sources + ["-Wl,--start-group", "-lm", "-lc", "-lgcc", "-Wl,--end-group"]
    row = {"workload": name, "category": "instrumentation" if name == "instrumentation-dummy" else "embench_workload", "status": "pending", "correctness": None,
           "measurement_kind": "rtl_simulation_smoke_not_hardware", "variant": "accepted_priming_on",
           "cycles": None, "retired_instructions": None, "cpi": None,
           "configured_clock_hz": None, "measured_clock_hz": None,
           "lut": None, "ff": None, "bram": None, "dsp": None, "setup_wns_ns": None, "hold_wns_ns": None,
           "warmup_heat": args.warmup, "global_scale_factor": args.scale,
           "evidence": str(work.relative_to(ROOT)), "firmware_sha256": None,
           "text_bytes": None, "data_bytes": None, "bss_bytes": None}
    result = command(compile_args, work, "firmware-build")
    if result:
        text = (work / "firmware-build.log").read_text(encoding="utf-8")
        row["status"] = ("memory_limited" if "overflowed" in text or "insufficient stack" in text else "timed_out" if result == 124 else "build_failed")
        return row
    if command([str(TOOL) + "size", elf], work, "size") or command([str(TOOL) + "objcopy", "-O", "binary", elf, work / "firmware.bin"], work, "objcopy"):
        raise RuntimeError("ELF inspection or conversion failed")
    if command([str(TOOL) + "objdump", "-d", elf], work, "disassembly"):
        raise RuntimeError("Disassembly failed")
    elf_bytes = elf.read_bytes()
    if elf_bytes[:6] != b"\x7fELF\x01\x01" or struct.unpack_from("<H", elf_bytes, 18)[0] != 243:
        raise ValueError("Expected little-endian ELF32 RISC-V firmware")
    flags = struct.unpack_from("<I", elf_bytes, 36)[0]
    if flags & 0xf:
        raise ValueError("ELF requires compressed instructions, hard-float ABI, or reduced registers")
    row["elf_flags"] = flags
    size_fields = (work / "size.log").read_text().splitlines()[-1].split()
    row.update(dict(zip(("text_bytes", "data_bytes", "bss_bytes"), map(int, size_fields[:3]))))
    binary = (work / "firmware.bin").read_bytes()
    if len(binary) > 65536:
        raise ValueError("Linked binary exceeds memory")
    padded = binary + bytes(65536 - len(binary))
    (work / "firmware.hex").write_text("".join(f"{int.from_bytes(padded[i:i+4], 'little'):08x}\n" for i in range(0, 65536, 4)), encoding="ascii")
    row["firmware_sha256"] = sha(work / "firmware.hex")
    row["elf_sha256"] = sha(elf)
    row["status"] = "built"
    return row


def execute_workload(run, executable, row, args):
    if row["status"] != "built":
        return
    work = ROOT / row["evidence"]
    result = command([executable, work / "uart.log", str(args.max_cycles)], work, "simulation", args.timeout)
    text = (work / "simulation.log").read_text(encoding="utf-8")
    if result:
        row["status"] = "memory_limited" if "Stack pointer exceeded" in text else "timed_out" if result == 124 or "cycle limit exceeded" in text else "verification_failed"
        row["failure_detail"] = text.strip().splitlines()[-1] if text.strip() else "No simulator output"
        row["correctness"] = False if row["status"] == "verification_failed" else None
        return
    uart = (work / "uart.log").read_text(encoding="ascii")
    found = re.fullmatch(r"EMBENCH cycles=0x([0-9a-f]{16}) retired=0x([0-9a-f]{16}) verified=1\n", uart)
    if not found or "PASS RTL Embench smoke" not in text:
        raise RuntimeError("Simulator exited without complete counter and correctness evidence")
    cycles, retired = [int(v, 16) for v in found.groups()]
    if not (0 < retired <= cycles <= args.max_cycles):
        raise ValueError("Invalid counter interval")
    observer = re.search(r"^OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)$", text, re.MULTILINE)
    if not observer or tuple(map(int, observer.groups()[:2])) != (cycles, retired):
        raise ValueError("Firmware counters disagree with independent simulator observations")
    row.update(status="passed", correctness=True, cycles=cycles, retired_instructions=retired,
               cpi=cycles / retired, minimum_sp=int(observer[3]), stack_high_water_bytes=65536-int(observer[3]),
               uart_sha256=sha(work / "uart.log"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workloads", nargs="*")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--with-dummy", action="store_true", help="Also measure the upstream empty benchmark as instrumentation context")
    parser.add_argument("--max-cycles", type=int, default=1000000000)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--scale", type=int, default=1)
    args = parser.parse_args()
    if not (1 <= args.max_cycles <= 1000000000000 and 1 <= args.timeout <= 7200 and 0 <= args.warmup <= 100 and 1 <= args.scale <= 10000):
        parser.error("Invalid experimental limits")
    lock = json.loads((ROOT / "third_party/SOURCES_LOCK.json").read_text(encoding="utf-8-sig"))
    names = args.workloads or lock["embench_workloads"]
    if len(names) != len(set(names)) or any(name not in lock["embench_workloads"] for name in names):
        parser.error("Workload selection is not a unique subset of pinned inventory")
    if args.with_dummy:
        names = ["instrumentation-dummy"] + names
    run = ROOT / "results" / ("embench-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    print("RUN " + str(run), flush=True)
    manifest = {"schema": 1, "started_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
                "protocol": "v3", "workloads": names, "all_workloads": lock["embench_workloads"], "stack_reservation_bytes": 16384,
                "limits": vars(args), "hardware_parameters": PARAMS, "results": [],
                "model_clock_hz": 100000000, "uart_model_clock_hz": 3200, "uart_model_baud": 100,
                "physical_implementation_measured": False, "official_embench_score": False}
    write_json(run / "manifest.json", manifest)
    try:
        _, input_hashes = source_snapshot(run)
        manifest["source_manifest_sha256"] = sha(run / "source-hashes.json")
        gcc = str(TOOL) + "gcc"
        manifest["compiler_version"] = subprocess.check_output([gcc, "--version"], text=True).splitlines()[0]
        manifest["compiler_sha256"] = sha(gcc)
        manifest["simulator_version"] = subprocess.check_output(["/usr/bin/verilator", "--version"], text=True).strip()
        manifest["libraries"] = {}
        for name in ("libc.a", "libm.a", "libgcc.a"):
            path = subprocess.check_output([gcc, "-march=rv32im", "-mabi=ilp32", "-print-file-name=" + name], text=True).strip()
            manifest["libraries"][name] = {"path": path, "sha256": sha(path)}
        write_json(run / "manifest.json", manifest)
        executable = None if args.build_only else build_simulator(run)
        if executable:
            manifest["simulator_executable_sha256"] = sha(executable)
        for name in names:
            print("BUILD " + name, flush=True)
            row = build_workload(run, name, args)
            if executable:
                print("RUN " + name + " " + row["status"], flush=True)
                execute_workload(run, executable, row, args)
            manifest["results"].append(row)
            write_json(run / "workloads" / name / "result.json", row)
            write_json(run / "manifest.json", manifest)
            print(name + ": " + row["status"] + " cycles=" + str(row["cycles"]), flush=True)
        for name, digest in input_hashes.items():
            if sha(run / "inputs" / name) != digest:
                raise ValueError("Run input changed during experiment: " + name)
        manifest["status"] = "completed_with_coverage_gaps" if any(r["status"] != ("built" if args.build_only else "passed") for r in manifest["results"]) else "completed"
        manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        write_json(run / "manifest.json", manifest)
        write_json(run / "results.json", manifest["results"])
        if manifest["results"]:
            fields = list(dict.fromkeys(key for row in manifest["results"] for key in row))
            with (run / "results.csv").open("w", newline="", encoding="utf-8-sig") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fields)
                writer.writeheader(); writer.writerows(manifest["results"])
    print("COMPLETE " + str(run), flush=True)


if __name__ == "__main__":
    main()
