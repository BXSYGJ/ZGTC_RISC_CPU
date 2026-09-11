import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
CPU = ROOT.parents[1]
sys.path.insert(0, str(CPU / "scripts"))
from load_use_profile import file_hash, require


def main(attempt=""):
    require(not attempt or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", attempt), "Invalid attempt label")
    output = ROOT / "build" / ("core-regressions" + ("-" + attempt if attempt else ""))
    output.mkdir(parents=True, exist_ok=False)
    modules = ("rv32_core", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv",
               "rv32_cache", "rv32_uncached", "rv32_memory_system", "rv32_burst_ram", "rv32_burst_arbiter")
    originals = {"rtl/" + name + ".sv": ROOT / (name + ".sv") if name in ("rv32_core", "rv32_btb") else BASE / "rtl" / (name + ".sv") for name in modules}
    originals.update({"sim/" + name: ROOT / "sim" / name for name in ("core_tb.sv", "cached_core_tb.sv")})
    originals["check_trace.py"] = BASE / "scripts/check_trace.py"
    originals.update({"core_selftest." + suffix: BASE / "build" / ("core_selftest." + suffix) for suffix in ("bin", "hex")})
    hashes = {}
    for relative, source in originals.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[relative] = file_hash(target)
    words = (output / "core_selftest.hex").read_text().splitlines()
    require(len(words) == 4096 and all(re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in words), "Invalid 16 KiB selftest image")
    image = b"".join(int(word, 16).to_bytes(4, "little") for word in words)
    binary = (output / "core_selftest.bin").read_bytes()
    require(image[:len(binary)] == binary and not any(image[len(binary):]), "Selftest HEX and binary disagree")
    shutil.copyfile(Path(__file__), output / "runner-original.py")
    record = {"schema": 1, "scope": "core/cached functional ISA trace and memory comparison; not timing or full external ISA certification",
              "passed": False, "source_hashes": hashes, "runner_sha256": file_hash(Path(__file__)), "commands": [], "runs": []}
    manifest = output / "manifest.json"

    def run(command, name, marker=None):
        record["commands"].append(list(map(str, command)))
        manifest.write_text(json.dumps(record, indent=2) + "\n")
        result = subprocess.run(command, capture_output=True, text=True, timeout=240)
        text = result.stdout + result.stderr
        (output / (name + ".log")).write_text(text)
        require(result.returncode == 0 and (marker is None or marker in text), "Regression failed: " + name)
        print(name + ": " + " | ".join(line for line in text.splitlines() if "PASS" in line), flush=True)

    for predictor in (0, 1):
        for cached in (False, True):
            bench = "cached_core_tb" if cached else "core_tb"
            mode = ("cached" if cached else "core") + f"-p{predictor}"
            executable = output / (mode + ".vvp")
            parameters = {"BTB_INDEX_BITS": 8, "EARLY_D_REQUEST": 1, "PREDICTOR": predictor}
            if cached:
                parameters.update(ICACHE_SET_BITS=9, DATA_OVERLAP=1, FAST_DCACHE_WRITE=1, FAST_DCACHE_READ=1,
                                  FETCH_OVERLAP=1, CACHE_SETS=6, ENABLE_CACHE=1, LOAD_USE_BUBBLE=1, FAST_ICACHE_HIT=1)
            command = ["iverilog", "-g2012", "-Wall", "-s", bench, "-o", str(executable)]
            command += [f"-P{bench}.{key}={value}" for key, value in parameters.items()]
            command += [str(output / "rtl" / (name + ".sv")) for name in (modules if cached else modules[:6])]
            command.append(str(output / "sim" / (bench + ".sv")))
            run(command, mode + "-compile")
            for seed in (("12345678",) if cached else ("12345678", "a5a5c3c3", "deadbeef")):
                name = mode + "-" + seed
                trace, memory = output / (name + ".trace"), output / (name + ".memory")
                run(["vvp", str(executable), "+firmware=" + str(output / "core_selftest.hex"),
                     "+trace=" + str(trace), "+memory_out=" + str(memory), "+seed=" + seed], name, "PASS ")
                run([sys.executable, str(output / "check_trace.py"), str(output / "core_selftest.bin"), str(trace), "--memory", str(memory)], name + "-reference", "PASS ")
                record["runs"].append({"name": name, "parameters": parameters, "seed": seed,
                                       "trace_sha256": file_hash(trace), "memory_sha256": file_hash(memory)})
    for relative, source in originals.items():
        require(file_hash(source) == hashes[relative] == file_hash(output / relative), "Regression source changed: " + relative)
    record.update(passed=True, outputs={path.name: file_hash(path) for path in output.iterdir() if path.is_file() and path.name != "manifest.json"})
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    print("PASS eight core/cached runs and independent trace/memory comparisons", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", default="")
    main(parser.parse_args().attempt)
