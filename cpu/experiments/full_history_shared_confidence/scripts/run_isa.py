import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run_command(command, log, expected_failure=None):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    log.write_text(output, encoding="utf-8")
    if expected_failure is None:
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}); see {log}")
    elif result.returncode == 0 or expected_failure not in output or "PASS ISA" in output:
        raise RuntimeError(f"Negative control did not fail as expected; see {log}")
    return output


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_firmware(project, source, build, prefix, name, input_path, defines=(), enable_m=False):
    base = build / name
    flags = ["-march=rv32im" if enable_m else "-march=rv32i", "-mabi=ilp32", "-nostdlib", "-nostartfiles", "-Wl,--no-relax"]
    run_command([prefix + "gcc", *flags, *defines,
                 "-I", project / "sim/isa", "-I", source / "isa/macros/scalar",
                 "-T", project / "sim/isa/link.ld", "-o", base.with_suffix(".elf"), input_path],
                base.with_suffix(".compile.log"))
    header = run_command([prefix + "readelf", "-h", "-A", base.with_suffix(".elf")], base.with_suffix(".elf.log"))
    if not re.search(r"Class:\s+ELF32", header) or not re.search(r"Machine:\s+RISC-V", header):
        raise RuntimeError(f"Wrong ISA object format: {name}")
    run_command([prefix + "objcopy", "-O", "binary", base.with_suffix(".elf"), base.with_suffix(".bin")],
                base.with_suffix(".objcopy.log"))
    run_command(["/usr/bin/python3", project / "scripts/bin_to_hex.py", base.with_suffix(".bin"),
                 base.with_suffix(".hex"), "--bytes", "65536"], base.with_suffix(".hex.log"))
    run_command([prefix + "objdump", "-d", base.with_suffix(".elf")], base.with_suffix(".dis"))
    run_command([prefix + "nm", "-n", base.with_suffix(".elf")], base.with_suffix(".symbols"))
    return base.with_suffix(".hex")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--tool-prefix", required=True)
    parser.add_argument("--load-use-bubble", type=int, choices=(0, 1), default=0)
    parser.add_argument("--fast-icache-hit", type=int, choices=(0, 1), default=0)
    parser.add_argument("--early-d-request", type=int, choices=(0, 1), default=0)
    parser.add_argument("--data-overlap", type=int, choices=(0, 1), default=0)
    parser.add_argument("--btb-index-bits", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--icache-set-bits", type=int, choices=range(0, 11), default=0)
    parser.add_argument("--fast-dcache-write", type=int, choices=(0, 1), default=0)
    parser.add_argument("--fast-dcache-read", type=int, choices=(0, 1), default=0)
    parser.add_argument("--fetch-overlap", type=int, choices=(0, 1), default=0)
    parser.add_argument("--enable-m", type=int, choices=(0, 1), default=0)
    parser.add_argument("--suite", choices=("rv32ui", "rv32um"), default="rv32ui")
    args = parser.parse_args()
    if args.suite == "rv32um" and not args.enable_m:
        parser.error("RV32UM requires --enable-m 1")
    project, source, build = args.project, args.source, args.build
    makefrag = (source / "isa" / args.suite / "Makefrag").read_text()
    match = re.search(args.suite + r"_sc_tests\s*=\s*\\\n(.*?)\n\n", makefrag, re.S)
    if not match:
        raise RuntimeError("Cannot identify upstream RV32UI test list")
    names = match.group(1).replace("\\", " ").split()
    if len(set(names)) != len(names) or any(not re.fullmatch(r"[a-z_]+", name) for name in names):
        raise RuntimeError("Invalid upstream test list")
    excluded = {"ma_data": "Requires transparent misaligned loads/stores; this CPU instead traps precisely."} if args.suite == "rv32ui" else {}
    if not set(excluded).issubset(names):
        raise RuntimeError("Pinned upstream exclusions no longer match")
    tests = [name for name in names if name not in excluded]
    if not tests:
        raise RuntimeError("Upstream test selection is empty")
    inputs = [source / "LICENSE", source / "isa" / args.suite / "Makefrag", source / "isa/macros/scalar/test_macros.h"]
    inputs += [source / "isa" / architecture / (name + ".S") for architecture in (args.suite, args.suite.replace("32", "64")) for name in names]
    inputs += [source / "isa/rv32ui/ma_data.S", source / "isa/rv64ui/ma_data.S"]
    manifest = {"started_utc": datetime.now(timezone.utc).isoformat(), "status": "running",
                "tests": tests, "excluded": excluded, "tool_prefix": args.tool_prefix,
                "load_use_bubble": args.load_use_bubble,
                "fast_icache_hit": args.fast_icache_hit,
                "early_d_request": args.early_d_request,
                "btb_index_bits": args.btb_index_bits,
                "icache_set_bits_override": args.icache_set_bits,
                "data_overlap": args.data_overlap,
                "fast_dcache_read": args.fast_dcache_read,
                "fast_dcache_write": args.fast_dcache_write,
                "fetch_overlap": args.fetch_overlap,
                "enable_m": args.enable_m, "suite": args.suite,
                "upstream_inputs": {str(path.relative_to(source)): digest(path) for path in inputs},
                "adapter_inputs": {str(path.relative_to(project)): digest(path)
                                   for path in [project / "sim/isa_tb.sv", project / "scripts/run_isa.py",
                                                project / "scripts/run_isa_tests.ps1", project / "scripts/bin_to_hex.py",
                                                *sorted((project / "sim/isa").iterdir())]},
                "rtl_inputs": {str(path.relative_to(project)): digest(path) for path in sorted((project / "rtl").glob("*.sv"))},
                "results": [], "negative_controls": []}
    result_path = build / "results.json"

    def save():
        result_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        configurations = [(0, 0, 4), (1, 0, 4), (0, 1, 1), (1, 1, 4)]
        sources = sorted((project / "rtl").glob("*.sv")) + [project / "sim/isa_tb.sv"]
        simulations = {}
        for predictor, cache, sets in configurations:
            config = f"p{predictor}_c{cache}_s{sets}"
            simulator = build / (config + ".vvp")
            run_command(["/usr/bin/iverilog", "-g2012", "-Wall", "-s", "isa_tb",
                         f"-Pisa_tb.PREDICTOR={predictor}", f"-Pisa_tb.ENABLE_CACHE={cache}",
                         f"-Pisa_tb.ICACHE_SET_BITS={args.icache_set_bits}", f"-Pisa_tb.CACHE_SETS={sets}", f"-Pisa_tb.LOAD_USE_BUBBLE={args.load_use_bubble}", f"-Pisa_tb.FAST_ICACHE_HIT={args.fast_icache_hit}", f"-Pisa_tb.DATA_OVERLAP={args.data_overlap}", f"-Pisa_tb.BTB_INDEX_BITS={args.btb_index_bits}", f"-Pisa_tb.EARLY_D_REQUEST={args.early_d_request}", f"-Pisa_tb.FAST_DCACHE_WRITE={args.fast_dcache_write}", f"-Pisa_tb.FAST_DCACHE_READ={args.fast_dcache_read}", f"-Pisa_tb.FETCH_OVERLAP={args.fetch_overlap}", f"-Pisa_tb.ENABLE_M={args.enable_m}", "-o", simulator, *sources], build / (config + ".compile.log"))
            simulations[config] = simulator
        for name in tests:
            image = compile_firmware(project, source, build, args.tool_prefix, name, source / "isa" / args.suite / (name + ".S"), enable_m=args.enable_m)
            for config, simulator in simulations.items():
                run_name = name + "_" + config
                output = run_command(["/usr/bin/vvp", simulator, f"+firmware={image}", f"+name={name}",
                                      f"+trace={build / (run_name + '.trace')}",
                                      f"+memory_out={build / (run_name + '.memory')}"], build / (run_name + ".log"))
                passed = re.findall(r"^PASS ISA name=(\w+) cycles=(\d+) retired=(\d+) predictor=(\d+) cache=(\d+) sets=(\d+) loadbubble=(\d+) fastihit=(\d+) m=(\d+) overlap=(\d+) fastdread=(\d+) earlyd=(\d+) btb=(\d+) dataoverlap=(\d+) fastdwrite=(\d+) isets=(\d+)$", output, re.M)
                if len(passed) != 1 or passed[0][0] != name:
                    raise RuntimeError(f"Missing or ambiguous success: {run_name}")
                entry = passed[0]
                if config != f"p{entry[3]}_c{entry[4]}_s{entry[5]}" or int(entry[6]) != args.load_use_bubble or int(entry[7]) != args.fast_icache_hit or int(entry[8]) != args.enable_m or int(entry[9]) != args.fetch_overlap or int(entry[10]) != args.fast_dcache_read or int(entry[11]) != args.early_d_request or int(entry[12]) != args.btb_index_bits or int(entry[13]) != args.data_overlap or int(entry[14]) != args.fast_dcache_write or int(entry[15]) != (args.icache_set_bits or int(entry[5])):
                    raise RuntimeError(f"Configuration mismatch: {run_name}")
                manifest["results"].append({"name": name, "configuration": config, "cycles": int(entry[1]),
                                            "retired": int(entry[2]), "hex_sha256": digest(image)})
                save()
            print(f"PASS upstream {args.suite.upper()} {name}: four configurations", flush=True)
        controls = [("negative_fail", project / "sim/isa/negative.S", ["-DNEGATIVE_KIND=1"], "ISA failure testnum=99"),
                    ("negative_trap", project / "sim/isa/negative.S", ["-DNEGATIVE_KIND=2"], "ISA unexpected trap cause=2"),
                    ("negative_timeout", project / "sim/isa/negative.S", ["-DNEGATIVE_KIND=3"], "ISA watchdog expired"),
                    ("ma_data", source / "isa/rv32ui/ma_data.S", [], "ISA unexpected trap cause=4")]
        for name, input_path, defines, expected in controls:
            image = compile_firmware(project, source, build, args.tool_prefix, name, input_path, defines, enable_m=args.enable_m)
            run_command(["/usr/bin/vvp", simulations["p1_c1_s4"], f"+firmware={image}", f"+name={name}",
                         f"+trace={build / (name + '.trace')}", f"+memory_out={build / (name + '.memory')}"],
                        build / (name + ".log"), expected_failure=expected)
            manifest["negative_controls"].append({"name": name, "expected_rejection": expected})
            save()
            print(f"PASS expected rejection: {name}", flush=True)
        manifest["status"] = "passed"
        print(f"PASS external {args.suite.upper()}: {len(tests)} tests, {len(manifest['results'])} runs, four rejection controls; not ISA certification.", flush=True)
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
