"""Build frozen CoreMark V0/V1 firmware and execute independently observed A/B runs."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
from uuid import uuid4

import run_embench as helper

ROOT = helper.ROOT
VARIANTS = Path('/mnt/d/AAAFPGA/ZGTC_RISC_CPU/cpu_paper/variants/accepted-153-valid-ram-v31-r1')
PORT = ROOT / "ports/coremark"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--console-delay-cycles", type=int, default=0)
    parser.add_argument("--clock-hz", type=int, choices=(120000000, 126000000, 132000000, 135000000, 141750000, 144000000, 145125000, 146250000, 148500000, 151200000, 153000000, 155250000, 157500000, 162000000), default=153000000)
    parser.add_argument("--architecture-run", type=Path, required=True)
    parser.add_argument("--directed-run", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100000:
        parser.error("Iterations must be between 1 and 100000")
    if args.console_delay_cycles not in (0,2700000):
        parser.error("Console pacing must be zero or the protocol-v6 value 2700000")
    variants = json.loads((VARIANTS / "manifest.json").read_text())
    identity = helper.sha(VARIANTS / "manifest.json")
    gates = {}
    for name, folder, filename, count in (("architecture", args.architecture_run, "manifest.json", 90),
                                          ("directed", args.directed_run, "manifest.json", 12)):
        path = folder.resolve() / filename
        if not path.is_relative_to((ROOT / "results").resolve()):
            raise ValueError("Gate must be within project results")
        gate = json.loads(path.read_text())
        if not (gate.get("passed") or gate.get("status")=="passed") or len(gate["runs"]) != count or gate["variant_manifest_sha256"] != identity:
            raise ValueError("Matching complete correctness gate required: " + name)
        gates[name] = {"path": str(path), "sha256": helper.sha(path)}
    run = ROOT / "results" / ("coremark-ablation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    record = {"schema": 1, "protocol": "v27", "firmware_port_protocol": "v6" if args.console_delay_cycles else "v4", "status": "running", "iterations": args.iterations,
              "console_delay_cycles": args.console_delay_cycles,
              "repetitions": 3, "gates": gates, "variant_manifest_sha256": identity,
              "measurement_kind": "matched_cycle_accurate_rtl_not_physical_score",
              "configured_clock_hz": args.clock_hz, "measured_clock_hz": None,
              "application_address": 4096, "loader_firmware_run": 'embench-loader-firmware-20260918T075837Z-7e6f9c1f',
              "stack_reservation_bytes": 16384, "hardware_parameters": helper.PARAMS,
              "results": [], "pairs": [], "firmware": [], "models": {}}
    def save():
        helper.write_json(run / "manifest.json", record)
        helper.write_json(run / "results.json", record["results"])
    save(); print("RUN " + str(run), flush=True)
    try:
        lock = json.loads((ROOT / "dependencies/COREMARK_LOCK.json").read_text(encoding="utf-8-sig"))
        for name, digest in lock["sha256"].items():
            original = ROOT / "dependencies/coremark" / name
            if helper.sha(original) != digest:
                raise ValueError("Pinned CoreMark source changed: " + name)
            helper.snapshot(original, run / "inputs/coremark" / name)
        helper.snapshot(ROOT / "dependencies/COREMARK_LOCK.json", run / "inputs/COREMARK_LOCK.json")
        for original in PORT.iterdir():
            if original.is_file():
                helper.snapshot(original, run / "inputs/port" / original.name)
        for name in ("start.S", "link_soc.ld"):
            helper.snapshot(helper.REFERENCE / "sw" / name, run / "inputs/port" / name)
        linker = run / "inputs/port/link_soc.ld"
        original = linker.read_bytes()
        if original.count(b"__stack_top - 4096") != 1:
            raise ValueError("Unexpected linker reservation")
        helper.snapshot(linker, run / "inputs/reference_link_soc.ld")
        if original.count(b"ORIGIN = 0, LENGTH = 64K") != 1: raise ValueError("Unexpected RAM region")
        linker.write_bytes(original.replace(b"__stack_top - 4096", b"__stack_top - 16384").replace(b"ORIGIN = 0, LENGTH = 64K", b"ORIGIN = 0x1000, LENGTH = 60K"))
        for name in ("protocol_v1.md", "protocol_v2.md", "protocol_v3.md", "protocol_v4.md"):
            helper.snapshot(ROOT / name, run / "inputs" / name)
        if args.console_delay_cycles:
            helper.snapshot(ROOT / "protocol_v6.md",run / "inputs/protocol_v6.md")
        helper.snapshot(Path(__file__), run / "inputs/runner.py")
        helper.snapshot(Path(helper.__file__), run / "inputs/run_embench.py")
        helper.snapshot(ROOT / "scripts/prepare_coremark_port.py", run / "inputs/prepare_coremark_port.py")
        helper.snapshot(helper.REFERENCE / "scripts/check_coremark.py", run / "inputs/check_coremark.py")
        from selected_coremark_clock import prepare
        prepare(run / "inputs/check_coremark.py", args.clock_hz)
        helper.snapshot(ROOT / "scripts/selected_coremark_clock.py", run / "inputs/selected_coremark_clock.py")
        spec = importlib.util.spec_from_file_location("frozen_coremark_checker", run / "inputs/check_coremark.py")
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        hashes = {p.relative_to(run / "inputs").as_posix(): helper.sha(p) for p in (run / "inputs").rglob("*") if p.is_file()}
        helper.write_json(run / "source-hashes.json", hashes)
        gcc = str(helper.TOOL) + "gcc"
        record["compiler_version"] = subprocess.check_output([gcc, "--version"], text=True).splitlines()[0]
        record["compiler_sha256"] = helper.sha(gcc)
        record["simulator_version"] = subprocess.check_output(["/usr/bin/verilator", "--version"], text=True).strip()
        libgcc = subprocess.check_output([gcc, "-march=rv32im", "-mabi=ilp32", "-print-libgcc-file-name"], text=True).strip()
        record["libgcc"] = {"path": libgcc, "sha256": helper.sha(libgcc)}
        models = {}
        for mode in (() if args.build_only else ('priming_off', 'priming_on', 'accepted_valid_ram')):
            model = run / "models" / mode
            (model / "inputs/rtl").mkdir(parents=True)
            for original in (VARIANTS / mode / "rtl").glob("*.sv"):
                if helper.sha(original) != variants["variants"][mode]["hashes"]["rtl/" + original.name]:
                    raise ValueError("Variant source changed")
                helper.snapshot(original, model / "inputs/rtl" / original.name)
            helper.snapshot(run / "inputs/port/sim_main.cpp", model / "inputs/port/sim_main.cpp")
            helper.snapshot(helper.PORT / "rv32_observed_soc.sv", model / "inputs/port/rv32_observed_soc.sv")
            model_hashes = {p.relative_to(model / "inputs").as_posix(): helper.sha(p) for p in (model / "inputs").rglob("*") if p.is_file()}
            helper.write_json(model / "source-hashes.json", model_hashes)
            models[mode] = helper.build_simulator(model)
            record["models"][mode] = {"inputs": model_hashes, "executable_sha256": helper.sha(models[mode])}
            save()
        for validation in (0, 1):
            label = "V" + str(validation)
            firmware = run / "firmware" / label
            firmware.mkdir(parents=True)
            port, upstream = run / "inputs/port", run / "inputs/coremark"
            flags = helper.FLAGS + ["-DTOTAL_DATA_SIZE=2000", f"-DITERATIONS={args.iterations}", f"-DVALIDATION_RUN={validation}",
                                    f"-DPERFORMANCE_RUN={1-validation}", f"-DCPU_CLOCK_HZ={args.clock_hz}u", f"-DCONSOLE_DELAY_CYCLES={args.console_delay_cycles}"]
            sources = [upstream / name for name in ("core_main.c", "core_list_join.c", "core_matrix.c", "core_state.c", "core_util.c")]
            sources += [port / name for name in ("core_portme.c", "ee_printf.c", "start.S")]
            command = [gcc] + flags + ['-DFLAGS_STR="' + " ".join(flags) + '"', "-I", port, "-I", upstream,
                       "-nostdlib", "-nostartfiles", "-Wl,--relax", "-Wl,--gc-sections", "-Wl,-Map=firmware.map",
                       "-T", port / "link_soc.ld", "-o", firmware / "firmware.elf"] + sources + ["-lgcc"]
            if helper.command(command, firmware, "firmware-build"):
                raise RuntimeError("CoreMark build failed: " + label)
            for suffix, tool_args in (("size", ["size", "firmware.elf"]), ("disassembly", ["objdump", "-d", "firmware.elf"]),
                                      ("objcopy", ["objcopy", "-O", "binary", "firmware.elf", "firmware.bin"])):
                if helper.command([str(helper.TOOL) + tool_args[0]] + tool_args[1:], firmware, suffix):
                    raise RuntimeError("CoreMark ELF inspection failed")
            elf = (firmware / "firmware.elf").read_bytes()
            if elf[:6] != b"\x7fELF\x01\x01" or struct.unpack_from("<H", elf, 18)[0] != 243 or struct.unpack_from("<I", elf, 36)[0] & 15:
                raise ValueError("Unexpected CoreMark ISA/ABI")
            binary = (firmware / "firmware.bin").read_bytes()
            if len(binary) > 45056:
                raise ValueError("CoreMark exceeds fixed memory partition")
            padded = bytes(4096) + binary + bytes(65536-4096-len(binary))
            (firmware / "firmware.hex").write_text("".join(f"{int.from_bytes(padded[i:i+4], 'little'):08x}\n" for i in range(0,65536,4)), encoding="ascii")
            sizes = list(map(int, (firmware / "size.log").read_text().splitlines()[-1].split()[:3]))
            info = {"configuration": label, "validation_run": bool(validation), "iterations": args.iterations,
                    "firmware_sha256": helper.sha(firmware / "firmware.hex"), "elf_sha256": helper.sha(firmware / "firmware.elf"),
                    "binary_sha256": helper.sha(firmware / "firmware.bin"), "binary_bytes": len(binary), "load_address": 4096,
                    "ram_crc32": format(__import__("zlib").crc32(binary), "08x"),
                    "text_bytes": sizes[0], "data_bytes": sizes[1], "bss_bytes": sizes[2], "flags": flags}
            record["firmware"].append(info); save()
            if args.build_only:
                print("BUILT " + label, flush=True)
                continue
            rows = []
            for repetition in range(1,4):
                order = ('priming_off', 'priming_on', 'accepted_valid_ram') if repetition != 2 else ('accepted_valid_ram', 'priming_on', 'priming_off')
                for mode in order:
                    work = run / "runs" / label / mode / str(repetition)
                    work.mkdir(parents=True)
                    helper.snapshot(firmware / "firmware.hex", work / "firmware.hex")
                    row = dict(info, variant=mode, repetition=repetition, status="pending", correctness=None,
                               cycles=None, retired_instructions=None, cpi=None, configured_clock_hz=args.clock_hz,
                               measured_clock_hz=None, lut=None, ff=None, bram=None, dsp=None, setup_wns_ns=None, hold_wns_ns=None,
                               placement_seed=None, evidence=str(work.relative_to(ROOT)))
                    record["results"].append(row); rows.append(row)
                    try:
                        code = helper.command([models[mode], work / "uart.log", "100000000000"], work, "simulation", 7200)
                        if code:
                            row["status"] = "timed_out" if code == 124 else "verification_failed"
                            raise RuntimeError("CoreMark simulation failed: " + str(work))
                        uart = (work / "uart.log").read_text()
                        parsed = checker.parse_result(uart, allow_short=True, expected_config=0x0e8e96fd, expected_clock_hz=args.clock_hz)
                        if parsed["validation_run"] != bool(validation) or parsed["iterations"] != args.iterations:
                            raise ValueError("CoreMark input mismatch")
                        text = (work / "simulation.log").read_text()
                        observer = re.search(r"^OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)$", text, re.MULTILINE)
                        if not observer or (int(observer[1]), int(observer[2])) != (parsed["cycles"], parsed["retired"]):
                            raise ValueError("CoreMark independent counter mismatch")
                        events = re.search(r"^EVENTS redirects=([0-9,]+) eligible=([0-9,]+) request_stalls=(\d+) response_waits=(\d+) barrier_cycles=(\d+)$", text, re.MULTILINE)
                        if not events:
                            raise ValueError("CoreMark missing event observations")
                        for prefix, values in (("redirect", events[1]), ("eligible", events[2])):
                            counts = list(map(int, values.split(",")))
                            if len(counts) != 7:
                                raise ValueError("Unexpected event class count")
                            row.update({prefix+"_"+kind: n for kind,n in zip(("conditional","jal","jalr","trap","mret","fence_i","other"),counts)})
                        row.update(request_stall_cycles=int(events[3]), response_wait_cycles=int(events[4]), barrier_cycles=int(events[5]),
                                   status="passed", correctness=True, cycles=parsed["cycles"], retired_instructions=parsed["retired"],
                                   cpi=parsed["cycles"]/parsed["retired"], minimum_sp=int(observer[3]), stack_high_water_bytes=65536-int(observer[3]),
                                   uart_sha256=helper.sha(work / "uart.log"), crc_valid=True, seed_crc=parsed["seed_crc"], final_crc=parsed["final_crc"],
                                   reportable_duration_at_configured_clock=parsed["reportable_duration"], physical_score_validated=False,
                                   cache_profile=parsed.get("profile"))
                    except Exception as error:
                        if row["status"] == "pending":
                            row["status"] = "verification_failed"
                        row["failure_detail"] = str(error)
                        raise
                    finally:
                        helper.write_json(work / "result.json", row); save()
                    print(f"{label} {mode} repeat={repetition}: cycles={row['cycles']} retired={row['retired_instructions']}", flush=True)
            off = [r for r in rows if r["variant"]=="priming_off"]
            for mode in ('priming_off', 'priming_on', 'accepted_valid_ram'):
                group=[r for r in rows if r["variant"]==mode]
                if len(group)!=3 or len({(r["cycles"],r["retired_instructions"]) for r in group})!=1:
                    raise ValueError("CoreMark deterministic repetition mismatch")
                if group[0]["retired_instructions"]!=off[0]["retired_instructions"]:
                    raise ValueError("CoreMark retirement mismatch requires trace investigation")
                a,b=off[0]["cycles"],group[0]["cycles"]
                record["pairs"].append(dict(configuration=label,variant=mode,baseline="priming_off",iterations=args.iterations,
                    status="passed",cycles_off=a,cycles_candidate=b,cycles_saved=a-b,speedup=a/b,
                    cycle_reduction_percent=100*(a-b)/a,firmware_sha256=info["firmware_sha256"]))
            save()
        for name,digest in hashes.items():
            if helper.sha(run / "inputs" / name) != digest:
                raise ValueError("Input mutated during execution")
        record["status"] = "built_not_executed" if args.build_only else "completed"
    except Exception as error:
        record.update(status="failed", error=str(error)); raise
    finally:
        save()
        for name in ("results", "pairs"):
            if record[name]:
                fields = list(dict.fromkeys(k for row in record[name] for k in row))
                with (run / (name+".csv")).open("w",encoding="utf-8-sig",newline="") as file:
                    writer=csv.DictWriter(file,fieldnames=fields); writer.writeheader(); writer.writerows(record[name])
    print("COMPLETE " + str(run), flush=True)


if __name__ == "__main__":
    main()
