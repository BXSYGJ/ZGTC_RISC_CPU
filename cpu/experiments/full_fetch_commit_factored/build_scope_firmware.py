import json
import re
import shutil
import subprocess
from pathlib import Path

from audit_fetch_inputs import ROOT, digest, require, load, audit_inputs
from audit_fetch_long import portable

BASE = ROOT.parent / "full_redirect_clock151200"
NAME = "scope_p0_s1224_t4590000000_rv32gcc_f153000000"
FLAGS = ["-march=rv32i", "-mabi=ilp32", "-msmall-data-limit=0", "-std=c11", "-O2", "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-nostdlib", "-nostartfiles", "-DCONSOLE_DELAY_CYCLES=0", "-DAPP_SAMPLE_CYCLES=1224", "-DAPP_TIMEOUT_CYCLES=4590000000ull", "-DAPP_CLOCK_HZ=153000000u", "-Wl,--no-relax"]


def validate_sources():
    record = load(ROOT / "scope-inputs.json")
    parent_manifest = BASE / "build/scope_p0_s1210_t4536000000_rv32gcc_f151200000.build.json"
    require(record["parent"] == BASE.name and digest(parent_manifest) == record["parent_manifest_sha256"], "Scope parent changed")
    parent = load(parent_manifest)
    expected_names = {"sw/scope.c", "sw/platform.h", "sw/start.S", "sw/link_soc.ld", "scripts/bin_to_hex.py"}
    require(set(record["source_hashes"]) == expected_names, "Incomplete scope source inventory")
    for relative, checksum in record["source_hashes"].items():
        require(digest(ROOT / relative) == checksum == digest(BASE / relative) == parent["SourceHashes"][relative], "Scope source changed: " + relative)
    require((record["clock_hz"], record["sample_cycles"], record["timeout_cycles"], record["console_delay_cycles"]) == (153000000, 1224, 4590000000, 0), "Scope configuration changed")
    return record, parent["Toolchain"]


def main():
    audit_inputs()
    sources, toolchain = validate_sources()
    evidence = ROOT / "build" / (NAME + "-evidence")
    evidence.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(Path(__file__), evidence / "generator-original.py")
    prefix = toolchain["Prefix"]
    require(re.fullmatch(r"/home/[A-Za-z0-9/._-]+/bin/riscv32-unknown-elf-", prefix) and ".." not in prefix.split("/"), "Invalid scope toolchain path")
    record = {"schema": 1, "scope": "unchanged scope software rebuilt for complete 153 MHz CPU; not runtime or hardware proof", "passed": False,
              "source_hashes": sources["source_hashes"], "source_inventory_sha256": digest(ROOT / "scope-inputs.json"),
              "generator_sha256": digest(Path(__file__)), "commands": []}
    receipt = evidence / "invocation.json"
    def run(command, name):
        native = ["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", *command]
        record["commands"].append(native)
        receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        result = subprocess.run(native, capture_output=True, text=True, encoding="utf-8", timeout=300)
        output = result.stdout + result.stderr
        (evidence / (name + ".log")).write_text(output, encoding="utf-8")
        require(result.returncode == 0, "Scope command failed: " + name)
        return output.strip()
    require(run([prefix + "gcc", "-dumpmachine"], "compiler-target") == toolchain["Target"] == "riscv32-unknown-elf", "Wrong scope target")
    require(run([prefix + "gcc", "-dumpfullversion"], "compiler-version") == toolchain["Version"] == "10.2.0", "Wrong scope compiler version")
    elf, binary, image = (ROOT / "build" / (NAME + suffix) for suffix in (".elf", ".bin", ".hex"))
    require(not any(path.exists() for path in (elf, binary, image)), "Scope output already exists")
    run([prefix + "gcc", *FLAGS, "-T", portable(ROOT / "sw/link_soc.ld"), "-o", portable(elf), portable(ROOT / "sw/start.S"), portable(ROOT / "sw/scope.c"), "-lgcc"], "compile")
    run([prefix + "objcopy", "-O", "binary", portable(elf), portable(binary)], "objcopy")
    run(["/usr/bin/python3", portable(ROOT / "scripts/bin_to_hex.py"), portable(binary), portable(image), "--bytes", "65536"], "hex")
    header = elf.read_bytes()[:20]
    require(header[:6] == bytes((127, 69, 76, 70, 1, 1)) and int.from_bytes(header[18:20], "little") == 243, "Wrong scope ELF architecture")
    words = image.read_text().splitlines()
    require(len(words) == 16384 and all(re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in words), "Scope HEX geometry changed")
    decoded = b"".join(int(word, 16).to_bytes(4, "little") for word in words)
    data = binary.read_bytes()
    require(decoded[:len(data)] == data and not any(decoded[len(data):]), "Scope binary and HEX disagree")
    validate_sources()
    hashes = dict(sources["source_hashes"])
    hashes["build_scope_firmware.py"] = digest(Path(__file__))
    metadata = {"RunName": NAME, "SampleCycles": 1224, "TimeoutCycles": 4590000000, "ConsoleDelayCycles": 0, "ClockHz": 153000000,
                "RecommendedUartBaud": 9600, "EnableM": 0, "Hex": str(image), "HexSha256": digest(image), "SourceHashes": hashes,
                "Toolchain": toolchain, "Flags": FLAGS, "ElfSha256": digest(elf), "BinSha256": digest(binary)}
    manifest = ROOT / "build" / (NAME + ".build.json")
    manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    record.update(passed=True, firmware_manifest_sha256=digest(manifest), outputs={path.name: digest(path) for path in (elf, binary, image)},
                  evidence_outputs={path.name: digest(path) for path in evidence.iterdir() if path.is_file() and path != receipt})
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
