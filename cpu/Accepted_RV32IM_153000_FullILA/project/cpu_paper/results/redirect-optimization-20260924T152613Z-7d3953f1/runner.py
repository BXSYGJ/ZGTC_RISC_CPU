"""Audited v27 screening with immutable RTL and the actual frozen v26 UART loader."""
import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4
import run_embench as h
import check_embench_loader_rtl as loader
from create_redirect_optimization import replace_once


def instrument(model):
    path = model / "inputs/port/rv32_observed_soc.sv"
    text = path.read_text()
    text = replace_once(text, "    output wire [2:0] redirect_kind", "    output wire [31:0] profile_target, profile_req_address,\n"
                        "    output wire [4:0] profile_state,\n"
                        "    output wire profile_req_valid, profile_req_ready, profile_rsp_valid, profile_rsp_ready,\n"
                        "    output wire [2:0] redirect_kind")
    text = replace_once(text, "endmodule", "    assign profile_target=soc.core.redirect_pc;\n"
                        "    assign profile_state={soc.core.frontend_barrier,soc.core.fetch_discard,soc.core.fetch_complete,soc.core.fetch_sent,soc.core.fetch_active};\n"
                        "    assign profile_req_address=soc.i_req_address;\n"
                        "    assign profile_req_valid=soc.i_req_valid;\n"
                        "    assign profile_req_ready=soc.i_req_ready;\n"
                        "    assign profile_rsp_valid=soc.i_rsp_valid;\n"
                        "    assign profile_rsp_ready=soc.i_rsp_ready;\nendmodule")
    path.write_text(text, encoding="utf-8")
    path = model / "inputs/port/sim_main.cpp"
    text = path.read_text()
    edits = {
        '#include <cstdint>': '#include <cstdint>\n#include <vector>\n#include <algorithm>\n#include <iterator>\n#include <map>',
        'if (argc != 3)': 'if (argc != 4)',
        'uint32_t sequence = 0, sp = 0, minimum_sp = 65536;': loader.SETUP + '\n        uint32_t sequence = 0, sp = 0, minimum_sp = 65536;',
        'uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;': loader.DRIVE + '\n            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;',
        'uart.put(char(byte)); std::cout.put(char(byte));': 'uart.put(char(byte)); std::cout.put(char(byte)); observed_uart.push_back(char(byte)); if (byte==75 && !sent_g) ++k_count;',
        '        for (uint64_t cycle = 1;': '        bool outstanding=false, stalled=false;\n        uint32_t stalled_address=0;\n        std::map<uint64_t,uint64_t> redirect_profile;\n        for (uint64_t cycle = 1;',
        '            bool retiring = model->retire_event;': '''            if (stalled && (!model->profile_req_valid || model->profile_req_address!=stalled_address))
                throw std::runtime_error("Instruction request changed under backpressure");
            stalled=model->profile_req_valid && !model->profile_req_ready;
            stalled_address=model->profile_req_address;
            if (model->profile_rsp_valid && model->profile_rsp_ready) {
                if (!outstanding) throw std::runtime_error("Instruction response without accepted request");
                outstanding=false;
            }
            if (model->profile_req_valid && model->profile_req_ready) {
                if (outstanding) throw std::runtime_error("Multiple outstanding instruction requests");
                outstanding=true;
            }
            uint64_t profile_key=(uint64_t(model->profile_target)<<8) | (model->profile_state<<3) | model->redirect_kind;
            bool retiring = model->retire_event;''',
        '                    ++redirects[kind];': '                    ++redirect_profile[profile_key];\n                    ++redirects[kind];',
        '                return 0;': '''                std::ofstream profile("redirect-profile.csv");
                profile << "target,fetch_state,kind,count\\n";
                for (const auto &entry:redirect_profile)
                    profile << (entry.first>>8) << ',' << ((entry.first>>3)&31) << ',' << (entry.first&7) << ',' << entry.second << '\\n';
                if (!profile) throw std::runtime_error("Profile write failed");
                return 0;''',
    }
    for before, after in edits.items():
        text = replace_once(text, before, after)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", type=Path, default=h.ROOT / "variants/redirect-optimization-v27-r1")
    parser.add_argument("--firmware", type=Path, default=h.ROOT / "results/embench-loader-firmware-20260918T075837Z-7e6f9c1f")
    parser.add_argument("--modes", nargs="+", default=["priming_off", "priming_on", "early_issue"])
    parser.add_argument("--workloads", nargs="+", default=["instrumentation-dummy", "crc32", "nsichneu", "sglib-combined"])
    parser.add_argument("--repetitions", type=int, choices=[1, 3], default=1)
    args = parser.parse_args()
    variants, firmware = args.variants.resolve(), args.firmware.resolve()
    vm = json.loads((variants / "manifest.json").read_text())
    fm = json.loads((firmware / "manifest.json").read_text())
    if vm["protocol"] != "v27" or fm["protocol"] != "v26" or fm["status"] != "built":
        raise ValueError("Frozen v27 variants and v26 firmware required")
    rows = {r["workload"]: r for r in fm["results"]}
    names = [n for n in rows if n != "uart-loader"] if args.workloads == ["all"] else args.workloads
    if len(set(names)) != len(names) or any(n not in rows or n == "uart-loader" for n in names):
        raise ValueError("Invalid workloads")
    if any(mode not in vm["variants"] for mode in args.modes):
        raise ValueError("Unknown variant")
    if h.sha(firmware / "source-hashes.json") != fm["source_manifest_sha256"]:
        raise ValueError("Firmware source manifest changed")
    for name, digest in json.loads((firmware / "source-hashes.json").read_text()).items():
        if h.sha(firmware / "inputs" / name) != digest:
            raise ValueError("Frozen firmware source changed: " + name)
    run = h.ROOT / "results" / ("redirect-optimization-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    record = dict(protocol="v27", status="running", qualification="screening_only_not_architectural_or_physical_qualification",
                  variant_manifest_sha256=h.sha(variants / "manifest.json"), variants=str(variants), firmware=str(firmware),
                  firmware_manifest_sha256=h.sha(firmware / "manifest.json"), configured_clock_hz=153000000,
                  measured_clock_hz=None, modes=args.modes, workloads=names, repetitions=args.repetitions, models={}, results=[])
    def save():
        h.write_json(run / "manifest.json", record)
        h.write_json(run / "results.json", record["results"])
        if record["results"]:
            with (run / "results.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, sorted(set().union(*(r.keys() for r in record["results"]))))
                writer.writeheader(); writer.writerows(record["results"])
    h.snapshot(__file__, run / "runner.py")
    for source in (Path(h.__file__), Path(loader.__file__), variants / "manifest.json", h.ROOT / "protocol_v27.md"):
        h.snapshot(source, run / "provenance" / source.name)
    save(); print("RUN " + str(run), flush=True)
    try:
        for mode in args.modes:
            model = run / "models" / mode
            for name, digest in vm["variants"][mode]["hashes"].items():
                if h.sha(variants / mode / name) != digest:
                    raise ValueError("Variant hash changed: " + mode + "/" + name)
                if name.startswith("rtl/"):
                    h.snapshot(variants / mode / name, model / "inputs" / name)
            for name in ("sim_main.cpp", "rv32_observed_soc.sv"):
                h.snapshot(firmware / "inputs/port" / name, model / "inputs/port" / name)
            instrument(model)
            hashes = {p.relative_to(model / "inputs").as_posix(): h.sha(p) for p in (model / "inputs").rglob("*") if p.is_file()}
            h.write_json(model / "source-hashes.json", hashes)
            executable = h.build_simulator(model)
            record["models"][mode] = dict(executable_sha256=h.sha(executable), source_manifest_sha256=h.sha(model / "source-hashes.json"))
            save()
            for name in names:
                for repetition in range(1, args.repetitions + 1):
                    work = run / "runs" / mode / name / str(repetition)
                    work.mkdir(parents=True)
                    source = rows[name]
                    for item, expected in ((firmware / "workloads/uart-loader/firmware.hex", rows["uart-loader"]["firmware_sha256"]),
                                           (firmware / "workloads" / name / "firmware.bin", source["binary_sha256"])):
                        if h.sha(item) != expected:
                            raise ValueError("Firmware bytes changed")
                    h.snapshot(firmware / "workloads/uart-loader/firmware.hex", work / "firmware.hex")
                    h.snapshot(firmware / "workloads" / name / "firmware.bin", work / "application.bin")
                    print("SIM " + mode + " " + name + " repeat=" + str(repetition), flush=True)
                    code = h.command([executable, work / "uart.log", "2500000000", work / "application.bin"], work, "simulation", 1800)
                    uart, log = (work / "uart.log").read_text(), (work / "simulation.log").read_text()
                    crc = re.search(r"BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n", uart)
                    result = re.search(r"EMBENCH cycles=0x([0-9a-f]{16}) retired=0x([0-9a-f]{16}) verified=1\n", uart)
                    observer = re.search(r"OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)", log)
                    valid = bool(code == 0 and crc and crc[1] == source["ram_crc32"] and int(crc[2], 16) == source["binary_bytes"]
                                 and result and observer and tuple(int(x,16) for x in result.groups()) == tuple(int(x) for x in observer.groups()[:2])
                                 and "EMBENCH FINISHED " + name + "\n" in uart)
                    row = dict(variant=mode, workload=name, repetition=repetition, status="passed" if valid else "failed",
                               cycles=None, retired_instructions=None, cpi=None, returncode=code,
                               application_sha256=h.sha(work / "application.bin"), loader_sha256=h.sha(work / "firmware.hex"),
                               uart_sha256=h.sha(work / "uart.log"), simulation_log_sha256=h.sha(work / "simulation.log"), evidence=str(work))
                    if valid:
                        row.update(cycles=int(result[1],16), retired_instructions=int(result[2],16),
                                   cpi=int(result[1],16)/int(result[2],16), minimum_sp=int(observer[3]),
                                   profile_sha256=h.sha(work / "redirect-profile.csv"))
                    record["results"].append(row); save()
                    print(json.dumps(row), flush=True)
                    if not valid:
                        break
            for name, digest in hashes.items():
                if h.sha(model / "inputs" / name) != digest:
                    raise ValueError("Model sources changed during execution")
        record["status"] = "screening_passed" if all(r["status"] == "passed" for r in record["results"]) else "screening_failed"
    except Exception as error:
        record.update(status="failed", error=str(error)); raise
    finally:
        save()
    print("DONE " + str(run), flush=True)


if __name__ == "__main__":
    main()
