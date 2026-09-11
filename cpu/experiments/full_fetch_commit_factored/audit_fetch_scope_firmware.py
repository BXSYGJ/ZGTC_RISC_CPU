import json
import re
from pathlib import Path

import build_scope_firmware as builder
from audit_fetch_inputs import ROOT, digest, require, load, audit_inputs


def audit_firmware(image=None):
    audit_inputs()
    sources, toolchain = builder.validate_sources()
    name = builder.NAME
    firmware = ROOT / "build" / (name + ".hex")
    manifest_path = ROOT / "build" / (name + ".build.json")
    metadata = load(manifest_path)
    evidence = ROOT / "build" / (name + "-evidence")
    record = load(evidence / "invocation.json")
    require(record.get("passed") is True, "Scope build incomplete")
    expected_hashes = dict(sources["source_hashes"])
    expected_hashes["build_scope_firmware.py"] = digest(ROOT / "build_scope_firmware.py")
    require(metadata["SourceHashes"] == expected_hashes, "Scope manifest source inventory differs")
    require(record["source_hashes"] == sources["source_hashes"] and record["source_inventory_sha256"] == digest(ROOT / "scope-inputs.json"), "Scope build input binding differs")
    require(record["generator_sha256"] == digest(evidence / "generator-original.py") == expected_hashes["build_scope_firmware.py"], "Scope builder changed")
    require(record["firmware_manifest_sha256"] == digest(manifest_path), "Scope manifest changed")
    require((metadata["RunName"], metadata["ClockHz"], metadata["SampleCycles"], metadata["TimeoutCycles"], metadata["ConsoleDelayCycles"], metadata["EnableM"], metadata["RecommendedUartBaud"]) == (name, 153000000, 1224, 4590000000, 0, 0, 9600), "Scope timebase or firmware ISA changed")
    require(metadata["Flags"] == builder.FLAGS and metadata["Toolchain"] == toolchain, "Scope flags or compiler identity differs")
    require(builder.portable(metadata["Hex"]) == builder.portable(firmware), "Scope output path differs")
    prefix = toolchain["Prefix"]
    elf, binary = (ROOT / "build" / (name + suffix) for suffix in (".elf", ".bin"))
    expected_commands = [[prefix + "gcc", "-dumpmachine"], [prefix + "gcc", "-dumpfullversion"],
                         [prefix + "gcc", *builder.FLAGS, "-T", builder.portable(ROOT / "sw/link_soc.ld"), "-o", builder.portable(elf), builder.portable(ROOT / "sw/start.S"), builder.portable(ROOT / "sw/scope.c"), "-lgcc"],
                         [prefix + "objcopy", "-O", "binary", builder.portable(elf), builder.portable(binary)],
                         ["/usr/bin/python3", builder.portable(ROOT / "scripts/bin_to_hex.py"), builder.portable(binary), builder.portable(firmware), "--bytes", "65536"]]
    require(record["commands"] == [["wsl.exe", "--distribution", "Ubuntu-22.04", "--exec", *command] for command in expected_commands], "Scope compiler command differs")
    require(record["outputs"] == {path.name: digest(path) for path in (elf, binary, firmware)}, "Scope output hashes differ")
    evidence_names = {"generator-original.py", "compiler-target.log", "compiler-version.log", "compile.log", "objcopy.log", "hex.log"}
    require(set(record["evidence_outputs"]) == evidence_names, "Scope build evidence inventory differs")
    for relative, checksum in record["evidence_outputs"].items():
        require(digest(evidence / relative) == checksum, "Scope compiler evidence changed: " + relative)
    require((evidence / "compiler-target.log").read_text().strip() == "riscv32-unknown-elf" and (evidence / "compiler-version.log").read_text().strip() == "10.2.0", "Scope compiler identity logs differ")
    require(metadata["HexSha256"] == digest(firmware) and metadata["ElfSha256"] == digest(elf) and metadata["BinSha256"] == digest(binary), "Scope metadata output hashes differ")
    header = elf.read_bytes()[:20]
    require(header[:6] == bytes((127, 69, 76, 70, 1, 1)) and int.from_bytes(header[18:20], "little") == 243, "Wrong scope ELF architecture")
    words = firmware.read_text().splitlines()
    require(len(words) == 16384 and all(re.fullmatch(r"[0-9a-fA-F]{8}", word) for word in words), "Scope HEX geometry differs")
    decoded = b"".join(int(word, 16).to_bytes(4, "little") for word in words)
    data = binary.read_bytes()
    require(0 < len(data) <= 65536 and decoded[:len(data)] == data and not any(decoded[len(data):]), "Scope binary and HEX disagree")
    if image is not None:
        require(digest(image) == digest(firmware), "Captured scope firmware differs")
    return {"scope": "source-bound 153 MHz application firmware; not runtime or hardware qualification", "passed": True,
            "firmware_sha256": digest(firmware), "manifest_sha256": digest(manifest_path), "build_receipt_sha256": digest(evidence / "invocation.json"),
            "clock_hz": 153000000, "sample_cycles": 1224, "timeout_cycles": 4590000000, "hardware_validated": False}


if __name__ == "__main__":
    print(json.dumps(audit_firmware(), indent=2))
