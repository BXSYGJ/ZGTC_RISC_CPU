"""Rebuild missing self-tests and validate matched variants without old build trees."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CPU = ROOT.parent / "cpu"
VARIANTS = ROOT / "variants/redirect-priming-v1"
PREFIX = str(ROOT / "tools/xpack-riscv-none-embed-gcc-10.2.0-1.2/bin/riscv-none-embed-")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = ROOT / "results" / ("architecture-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    source = run / "inputs"
    source.mkdir()
    originals = {
        "core_selftest.S": CPU / "experiments/full_redirect_clock151200/sw/core_selftest.S",
        "link.ld": CPU / "experiments/full_redirect_clock151200/sw/link.ld",
        "generate_random_body.py": CPU / "experiments/full_redirect_clock151200/scripts/generate_random_body.py",
        "check_trace.py": CPU / "experiments/full_redirect_clock151200/scripts/check_trace.py",
        "core_tb.sv": CPU / "experiments/full_relation_reuse1/sim/core_tb.sv",
        "cached_core_tb.sv": CPU / "experiments/full_relation_reuse1/sim/cached_core_tb.sv",
        "muldiv_interrupt.S": CPU / "experiments/full_redirect_clock151200/sw/muldiv_interrupt.S",
        "muldiv_link.ld": CPU / "experiments/full_redirect_clock151200/sim/isa/link.ld",
        "muldiv_core_tb.sv": CPU / "experiments/full_redirect_clock151200/sim/muldiv_core_tb.sv", "runner.py": Path(__file__)}
    for name, original in originals.items():
        shutil.copyfile(original, source / name)
    variant_manifest = json.loads((VARIANTS / "manifest.json").read_text())
    for mode in ("priming_off", "priming_on"):
        destination = source / mode
        destination.mkdir()
        for original in (VARIANTS / mode / "rtl").glob("*.sv"):
            if sha(original) != variant_manifest["variants"][mode]["rtl/" + original.name]["sha256"]:
                raise ValueError("Variant differs from its manifest")
            shutil.copyfile(original, destination / original.name)
    manifest = {"schema": 1, "scope": "matched RV32I self-test with independent architectural trace/memory reference plus RV32IM multiply/divide interrupt cases",
                "rv32i_selftest_memory_bytes": 16384, "m_extension_in_selftest": False,
                "m_extension_in_muldiv_tests": True, "program_seed": 20260906,
                "compiler_version": subprocess.check_output([PREFIX + "gcc", "--version"], text=True).splitlines()[0],
                "compiler_sha256": sha(Path(PREFIX + "gcc")), "variant_manifest_sha256": sha(VARIANTS / "manifest.json"),
                "input_hashes": {p.relative_to(source).as_posix(): sha(p) for p in source.rglob("*") if p.is_file()},
                "commands": [], "runs": [], "passed": False}
    def save():
        (run / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    def call(command, name, marker=None):
        command = list(map(str, command))
        manifest["commands"].append({"name": name, "argv": command, "cwd": str(run), "timeout_seconds": 240}); save()
        with (run / (name + ".log")).open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=run, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        text = (run / (name + ".log")).read_text(encoding="utf-8")
        if completed.returncode or (marker and marker not in text):
            raise RuntimeError("Regression failed: " + str(run / (name + ".log")))
        return text
    def image(name, size):
        call([PREFIX + "objcopy", "-O", "binary", run / (name + ".elf"), run / (name + ".bin")], name + "-objcopy")
        binary = (run / (name + ".bin")).read_bytes()
        if len(binary) > size:
            raise ValueError("Self-test image too large")
        binary += bytes(size-len(binary))
        (run / (name + ".hex")).write_text("".join(f"{int.from_bytes(binary[i:i+4],'little'):08x}\n" for i in range(0,size,4)), encoding="ascii")
    print("RUN " + str(run), flush=True)
    save()
    try:
        call([sys.executable, "-B", source / "generate_random_body.py", run / "random_body.inc", "--seed", "20260906"], "generate-program")
        common = ["-mabi=ilp32", "-mcmodel=medany", "-nostdlib", "-nostartfiles", "-Wl,--no-relax"]
        call([PREFIX + "gcc", "-march=rv32i"] + common + ["-I", run, "-T", source / "link.ld", "-o", run / "core_selftest.elf", source / "core_selftest.S"], "selftest-build")
        image("core_selftest", 16384)
        call([PREFIX + "gcc", "-march=rv32im"] + common + ["-T", source / "muldiv_link.ld", "-o", run / "muldiv_interrupt.elf", source / "muldiv_interrupt.S"], "muldiv-build")
        image("muldiv_interrupt", 65536)
        symbols = call([PREFIX + "nm", "-n", run / "muldiv_interrupt.elf"], "muldiv-symbols")
        addresses = {name: address for address, name in re.findall(r"^([0-9a-f]{8}) T (target_div|target_mul|target_mulh)$", symbols, re.MULTILINE)}
        if len(addresses) != 3:
            raise ValueError("Missing multiply/divide interrupt targets")
        manifest["firmware_hashes"] = {p.name: sha(p) for p in run.glob("*.hex")}
        modules = ["rv32_core", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv",
                   "rv32_cache", "rv32_uncached", "rv32_memory_system", "rv32_burst_ram", "rv32_burst_arbiter"]
        for mode in ("priming_off", "priming_on"):
            rtl = source / mode
            for predictor in (0, 1):
                for cached, bubble in ((False, 0), (False, 1), (True, 0), (True, 1)):
                    bench = "cached_core_tb" if cached else "core_tb"
                    name = f"{mode}-{'cached' if cached else 'core'}-p{predictor}-l{bubble}"
                    params = {"BTB_INDEX_BITS": 8, "EARLY_D_REQUEST": 1, "PREDICTOR": predictor, "LOAD_USE_BUBBLE": bubble}
                    if cached:
                        params.update(ICACHE_SET_BITS=9, DATA_OVERLAP=1, FAST_DCACHE_WRITE=1, FAST_DCACHE_READ=1,
                                      FETCH_OVERLAP=1, CACHE_SETS=6, ENABLE_CACHE=1, FAST_ICACHE_HIT=1)
                    executable = run / (name + ".vvp")
                    call(["/usr/bin/iverilog", "-g2012", "-Wall", "-s", bench, "-o", executable] +
                         [f"-P{bench}.{key}={value}" for key,value in params.items()] +
                         [rtl / (module + ".sv") for module in (modules if cached else modules[:6])] + [source / (bench + ".sv")], name + "-compile")
                    for seed in (("12345678",) if cached else ("12345678", "a5a5c3c3", "deadbeef")):
                        label = name + "-" + seed
                        trace, memory = run / (label + ".trace"), run / (label + ".memory")
                        call(["/usr/bin/vvp", executable, "+firmware=" + str(run / "core_selftest.hex"),
                              "+trace=" + str(trace), "+memory_out=" + str(memory), "+seed=" + seed], label, "PASS ")
                        check = call([sys.executable, "-B", source / "check_trace.py", run / "core_selftest.bin", trace, "--memory", memory], label + "-reference", "PASS reference")
                        manifest["runs"].append({"kind": "architecture", "variant": mode, "name": label, "parameters": params,
                                                 "simulation_seed": seed, "passed": True, "trace_sha256": sha(trace), "memory_sha256": sha(memory), "reference_output": check.strip()})
                        save(); print("PASS " + label, flush=True)
            for bubble in (0, 1):
                name = f"{mode}-muldiv-l{bubble}"
                executable = run / (name + ".vvp")
                params = {"BTB_INDEX_BITS": 8, "EARLY_D_REQUEST": 1, "FETCH_OVERLAP": 1, "LOAD_USE_BUBBLE": bubble}
                call(["/usr/bin/iverilog", "-g2012", "-Wall", "-s", "muldiv_core_tb", "-o", executable] +
                     [f"-Pmuldiv_core_tb.{k}={v}" for k,v in params.items()] + [rtl / (m + ".sv") for m in modules[:6]] + [source / "muldiv_core_tb.sv"], name + "-compile")
                for target, delays in (("target_div", (0,1,15,30)), ("target_mul", (0,)), ("target_mulh", (0,1))):
                    for delay in delays:
                        label = f"{name}-{target}-{delay}"
                        text = call(["/usr/bin/vvp", executable, "+firmware=" + str(run / "muldiv_interrupt.hex"),
                                     "+irq_pc=" + addresses[target], f"+irq_delay={delay}"], label, "PASS muldiv_core checks=2")
                        manifest["runs"].append({"kind": "muldiv_interrupt", "variant": mode, "name": label, "passed": True, "parameters": params, "output": text.strip()})
                        save()
                print("PASS " + name + " (7 interrupt cases)", flush=True)
        if len(manifest["runs"]) != 60:
            raise ValueError("Incomplete 32 architectural and 28 interrupt run matrix")
        for name, digest in manifest["input_hashes"].items():
            if sha(source / name) != digest:
                raise ValueError("Regression input changed")
        manifest["passed"] = True
    except Exception as error:
        manifest["error"] = str(error)
        raise
    finally:
        save()
    print("PASS 60 matched regression runs: " + str(run), flush=True)


if __name__ == "__main__":
    main()
