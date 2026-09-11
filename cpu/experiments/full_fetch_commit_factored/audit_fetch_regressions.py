import json
import re
import sys
from pathlib import Path

from audit_fetch_inputs import ROOT, PARENT, digest, require, load, audit_inputs

FUNCTIONAL = ROOT / "build/fetch-tests-e9c9a259"
REGRESSION = ROOT / "build/core-regressions"
BASE = ROOT.parent / "full_redirect_clock151200"
OBSERVER = ROOT.parent / "full_relation_reuse1"
MODULES = ("rv32_core", "rv32_machine", "rv32_decode", "rv32_alu", "rv32_btb", "rv32_muldiv",
           "rv32_cache", "rv32_uncached", "rv32_memory_system", "rv32_burst_ram", "rv32_burst_arbiter")


def functional():
    record = load(FUNCTIONAL / "manifest.json")
    require(record["passed"] is True and record["sources_unchanged"] is True and record["tests_run"] == 5, "Fetch functional suite incomplete")
    paths = [ROOT / name for name in ("test_fetch_commit.py", "fetch_commit_tb.sv", "fetch_enable_tb.sv", "redirect_prime_tb.sv", "change-receipt.json")]
    paths += [ROOT / "rtl" / (name + ".sv") for name in MODULES[:6]]
    paths.append(PARENT / "rtl/rv32_core.sv")
    require(record["sources"] == {str(path): digest(path) for path in paths}, "Fetch functional input inventory changed")
    names = {"candidate.sv", "reference.sv", "test.vvp", "compile.log", "execute.log", "invocation.json"}
    require({Path(name).as_posix() for name in record["outputs"]} == {"case-" + str(index) + "/" + name for index in range(1, 16) for name in names}, "Fetch functional outputs incomplete")
    for relative, checksum in record["outputs"].items():
        require(digest(FUNCTIONAL / relative) == checksum, "Fetch functional artifact changed")
    require(len(record["runs"]) == 15, "Fetch case count differs")
    positive = set()
    negative = []
    for index, entry in enumerate(record["runs"], 1):
        stage = FUNCTIONAL / ("case-" + str(index))
        require(load(stage / "invocation.json") == entry, "Fetch invocation differs")
        require(entry["passed"] is True and entry["compile_exit"] == 0, "Fetch compilation incomplete")
        require(set(entry["outputs"]) == names - {"invocation.json"}, "Fetch case output inventory incomplete")
        for name, checksum in entry["outputs"].items():
            require(digest(stage / name) == checksum, "Fetch case output changed")
        bench = entry["bench"]
        require(bench in {"fetch_commit_tb", "fetch_enable_tb", "redirect_prime_tb"}, "Unexpected fetch bench")
        command = ["iverilog", "-g2012", "-s", bench, f"-P{bench}.FETCH_OVERLAP={entry['overlap']}"]
        if bench != "fetch_enable_tb":
            command.append(f"-P{bench}.PREDICTOR={entry['predictor']}")
        command += ["-o", str(stage / "test.vvp"), str(stage / "candidate.sv"), str(stage / "reference.sv")]
        command += [str(ROOT / "rtl" / (name + ".sv")) for name in MODULES[1:6]]
        command.append(str(ROOT / (bench + ".sv")))
        require(entry["compile_command"] == command and entry["execute_command"] == ["vvp", str(stage / "test.vvp")], "Fetch command differs")
        source = (ROOT / "rtl/rv32_core.sv").read_text(encoding="utf-8")
        if entry["mutation"]:
            before, after = entry["mutation"]
            require(source.count(before) == 1, "Bad compiled mutation")
            source = source.replace(before, after)
            negative.append(tuple(entry["mutation"]))
            require(bench == "fetch_commit_tb" and entry["overlap"] == entry["predictor"] == 1 and entry["execute_exit"] != 0, "Mutation was not rejected")
            require("FAIL fetch_commit" in (stage / "execute.log").read_text(), "Missing runtime mutation rejection")
        else:
            positive.add((bench, entry["overlap"], entry["predictor"]))
            require(entry["execute_exit"] == 0, "Positive fetch execution failed")
            output = (stage / "execute.log").read_text()
            if bench == "fetch_enable_tb":
                require("PASS fetch_enable combinations=256 checks=512" in output, "Incomplete Boolean coverage")
            elif bench == "redirect_prime_tb":
                require("PASS redirect_prime cases=35 checks=444" in output, "Incomplete redirect coverage")
            else:
                require(re.search(r"PASS fetch_commit checks=[1-9][0-9]* extra=0 flush=[1-9][0-9]* barrier=[1-9][0-9]* held=[1-9][0-9]* overlap=", output), "Missing exact-state or backpressure coverage")
                if entry["overlap"]:
                    require("overlap=949" in output, "Missing overlap transfers")
        require((stage / "candidate.sv").read_text(encoding="utf-8") == source, "Executed candidate differs")
        require((stage / "reference.sv").read_text(encoding="utf-8") == (PARENT / "rtl/rv32_core.sv").read_text(encoding="utf-8").replace("module rv32_core #(", "module rv32_core_reference #("), "Executed parent differs")
    expected = {(bench, overlap, predictor) for bench in ("fetch_commit_tb", "redirect_prime_tb") for overlap in (0, 1) for predictor in (0, 1)}
    expected |= {("fetch_enable_tb", overlap, 1) for overlap in (0, 1)}
    require(positive == expected and len(negative) == len(set(negative)) == 5, "Incomplete positive or fault matrix")
    return {"directory": str(FUNCTIONAL), "manifest_sha256": digest(FUNCTIONAL / "manifest.json")}


def regression():
    record = load(REGRESSION / "manifest.json")
    require(record["passed"] is True and record["runner_sha256"] == digest(ROOT / "run_regressions.py"), "Core regression incomplete or runner changed")
    originals = {"rtl/" + name + ".sv": ROOT / "rtl" / (name + ".sv") for name in MODULES}
    originals.update({"sim/" + name: OBSERVER / "sim" / name for name in ("core_tb.sv", "cached_core_tb.sv")})
    originals.update({"check_trace.py": BASE / "scripts/check_trace.py", "observer-receipt.json": OBSERVER / "observer-receipt.json"})
    originals.update({"core_selftest." + suffix: BASE / "build" / ("core_selftest." + suffix) for suffix in ("bin", "hex")})
    require(record["source_hashes"] == {relative: digest(path) for relative, path in originals.items()}, "Core regression source inventory changed")
    for relative, source in originals.items():
        require(digest(REGRESSION / relative) == digest(source), "Captured core regression input changed")
    expected_names = {kind + "-p" + str(predictor) + "-l" + str(bubble) + "-" + seed
                      for kind in ("core", "cached") for predictor in (0, 1) for bubble in (0, 1)
                      for seed in (("12345678", "a5a5c3c3", "deadbeef") if kind == "core" else ("12345678",))}
    require(len(record["runs"]) == 16 and {entry["name"] for entry in record["runs"]} == expected_names, "Wrong core regression matrix")
    expected_outputs = {name + suffix for name in expected_names for suffix in (".trace", ".memory", ".log", "-reference.log")}
    expected_outputs |= {kind + "-p" + str(predictor) + "-l" + str(bubble) + suffix for kind in ("core", "cached") for predictor in (0, 1) for bubble in (0, 1) for suffix in (".vvp", "-compile.log")}
    expected_outputs |= {"check_trace.py", "core_selftest.hex", "core_selftest.bin", "observer-receipt.json", "runner-original.py"}
    require(set(record["outputs"]) == expected_outputs, "Incomplete regression output inventory")
    for name, checksum in record["outputs"].items():
        require(digest(REGRESSION / name) == checksum, "Core regression artifact changed")
    commands = []
    ordered = []
    for predictor in (0, 1):
        for cached, bubble in ((False, 0), (False, 1), (True, 0), (True, 1)):
            bench = "cached_core_tb" if cached else "core_tb"
            mode = ("cached" if cached else "core") + f"-p{predictor}-l{bubble}"
            parameters = {"BTB_INDEX_BITS": 8, "EARLY_D_REQUEST": 1, "PREDICTOR": predictor, "LOAD_USE_BUBBLE": bubble}
            if cached:
                parameters.update(ICACHE_SET_BITS=9, DATA_OVERLAP=1, FAST_DCACHE_WRITE=1, FAST_DCACHE_READ=1, FETCH_OVERLAP=1, CACHE_SETS=6, ENABLE_CACHE=1, LOAD_USE_BUBBLE=bubble, FAST_ICACHE_HIT=1)
            executable = REGRESSION / (mode + ".vvp")
            command = ["iverilog", "-g2012", "-Wall", "-s", bench, "-o", str(executable)]
            command += [f"-P{bench}.{key}={value}" for key, value in parameters.items()]
            command += [str(REGRESSION / "rtl" / (name + ".sv")) for name in (MODULES if cached else MODULES[:6])]
            command.append(str(REGRESSION / "sim" / (bench + ".sv")))
            commands.append(command)
            for seed in (("12345678",) if cached else ("12345678", "a5a5c3c3", "deadbeef")):
                name = mode + "-" + seed
                trace, memory = REGRESSION / (name + ".trace"), REGRESSION / (name + ".memory")
                commands.append(["vvp", str(executable), "+firmware=" + str(REGRESSION / "core_selftest.hex"), "+trace=" + str(trace), "+memory_out=" + str(memory), "+seed=" + seed])
                commands.append([sys.executable, str(REGRESSION / "check_trace.py"), str(REGRESSION / "core_selftest.bin"), str(trace), "--memory", str(memory)])
                entry = record["runs"][len(ordered)]
                require(entry["name"] == name and entry["parameters"] == parameters and entry["seed"] == seed, "Regression parameters differ")
                require(entry["trace_sha256"] == digest(trace) and entry["memory_sha256"] == digest(memory), "Trace or memory binding differs")
                require("PASS reference" in (REGRESSION / (name + "-reference.log")).read_text(), "Reference comparison incomplete")
                log = (REGRESSION / (name + ".log")).read_text()
                match = re.search(r"PASS relation reuse=([0-9]+) mem=([0-9]+) wb=([0-9]+) stalls=([0-9]+) load=([0-9]+) bubble=([01])", log)
                require(match and entry["relation_coverage"] == dict(zip(("reuse", "mem", "wb", "stalls", "load"), map(int, match.groups()[:5]))) and int(match[6]) == bubble, "Actual forwarding coverage differs")
                ordered.append(name)
    require(record["commands"] == commands, "Core regression command sequence differs")
    return {"directory": str(REGRESSION), "manifest_sha256": digest(REGRESSION / "manifest.json")}


def audit_regressions():
    audit_inputs()
    return {"schema": 1, "passed": True, "functional": functional(), "core": regression(), "hardware_validated": False}


if __name__ == "__main__":
    result = audit_regressions()
    (ROOT / "build/regression-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
