import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_physical import digest, require

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "full_redirect_clock151200"
CPU = ROOT.parents[1]
REVISION = "2ebecad997fa58cd9e5724340ba75aa4b59bd1d0"
ARCHIVE_SHA256 = "1B6BBCA3A60B81FD3B94FA5DB6497D48918944C80C74E5BCF39BBD5DDC63C483"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    output = ROOT / "build/external-isa"
    output.mkdir(parents=True, exist_ok=False)
    project = output / "project"
    source = output / "upstream"
    project.mkdir()
    source.mkdir()
    archive = CPU / "build" / ("riscv-tests-" + REVISION + ".tar.gz")
    require(digest(archive) == ARCHIVE_SHA256, "Pinned upstream archive changed")
    toolchain = read_json(BASE / "build/riscv32-toolchain.json")
    prefix = toolchain["ToolPrefix"]
    require(re.fullmatch(r"/home/[A-Za-z0-9/._-]+/bin/riscv32-unknown-elf-", prefix) and ".." not in prefix.split("/"), "Invalid toolchain path")
    inventory = read_json(ROOT / "build/physical-project-complete-inputs.json")["source_hashes"]
    originals = {relative: ROOT / "build/physical-project-complete" / relative for relative in inventory}
    for relative in ("sim/isa_tb.sv", "scripts/run_isa.py", "scripts/run_isa_tests.ps1", "scripts/bin_to_hex.py"):
        originals[relative] = BASE / relative
    for path in (BASE / "sim/isa").iterdir():
        require(path.is_file(), "Unexpected nested ISA adapter directory")
        originals["sim/isa/" + path.name] = path
    hashes = {}
    for relative, original in originals.items():
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        hashes[relative] = digest(destination)
        if relative in inventory:
            require(hashes[relative] == inventory[relative], "Physical-stage RTL changed")
    shutil.copyfile(Path(__file__), output / "runner-original.py")
    record = {"schema": 1, "scope": "pinned upstream RV32UI/RV32UM runs on current RTL; four configurations, not complete ISA certification",
              "passed": False, "revision": REVISION, "archive_sha256": ARCHIVE_SHA256,
              "inputs": hashes, "runner_sha256": digest(Path(__file__)), "commands": [], "suites": {}}
    manifest = output / "invocation.json"

    def run(command, name):
        record["commands"].append(list(map(str, command)))
        manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True, timeout=1200)
        text = result.stdout + result.stderr
        (output / (name + ".log")).write_text(text, encoding="utf-8")
        require(result.returncode == 0, "External ISA command failed: " + name)
        return text

    require(run([prefix + "gcc", "-dumpmachine"], "compiler-target").strip() == "riscv32-unknown-elf", "Wrong compiler target")
    require(run([prefix + "gcc", "-dumpfullversion"], "compiler-version").strip() == toolchain["CompilerVersion"] == "10.2.0", "Wrong compiler version")
    record["tool_sha256"] = {name: digest(Path(prefix + name)) for name in ("gcc", "objcopy", "objdump", "readelf", "nm")}
    run(["tar", "-xf", str(archive), "-C", str(source), "--strip-components=1"], "extract-upstream")
    for suite in ("rv32ui", "rv32um"):
        build = output / suite
        build.mkdir()
        command = [sys.executable, str(project / "scripts/run_isa.py"), "--project", str(project), "--source", str(source),
                   "--build", str(build), "--tool-prefix", prefix, "--suite", suite, "--enable-m", "1",
                   "--load-use-bubble", "1", "--fast-icache-hit", "1", "--fetch-overlap", "1",
                   "--fast-dcache-read", "1", "--fast-dcache-write", "1", "--early-d-request", "1",
                   "--data-overlap", "1", "--btb-index-bits", "8", "--icache-set-bits", "9"]
        text = run(command, suite)
        result = read_json(build / "results.json")
        require(result["status"] == "passed" and result["suite"] == suite, "ISA suite did not pass")
        require(len(result["results"]) == len(result["tests"]) * 4 and len(result["negative_controls"]) == 4, "Incomplete ISA configuration or rejection coverage")
        for relative, expected in result["rtl_inputs"].items():
            require(expected.upper() == inventory[relative] == hashes[relative] == digest(project / relative), "ISA RTL differs from physical candidate")
        for relative, expected in result["upstream_inputs"].items():
            require(digest(source / relative) == expected.upper(), "Upstream source changed")
        for relative, expected in result["adapter_inputs"].items():
            require(digest(project / relative) == expected.upper() == hashes[relative], "ISA adapter changed")
        record["suites"][suite] = {"tests": len(result["tests"]), "runs": len(result["results"]),
                                   "negative_controls": 4, "excluded": result["excluded"], "results_sha256": digest(build / "results.json"),
                                   "artifact_sha256": {path.name: digest(path) for path in build.iterdir() if path.is_file()}}
        print("\n".join(line for line in text.splitlines() if "PASS" in line), flush=True)
    for relative, original in originals.items():
        require(digest(original) == hashes[relative] == digest(project / relative), "ISA input changed during run: " + relative)
    record.update(passed=True, outputs={path.name: digest(path) for path in output.iterdir() if path.is_file() and path.name != "invocation.json"})
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("PASS pinned external ISA source/firmware/result bindings", flush=True)


if __name__ == "__main__":
    main()
