import hashlib
import json
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parent
NAME = "scope_p0_s1210_t4536000000_rv32gcc_f151200000"
EXPECTED_HASH = "72BE13E1AABEDFBEDF7EA2DE4A97DC49ECA020FDB2158DA64582ADF89C32655E"
EXPECTED_SOURCES = {"sw/scope.c", "sw/platform.h", "sw/start.S", "sw/link_soc.ld",
                    "scripts/bin_to_hex.py", "scripts/build_scope.ps1"}


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(firmware_path, experiment=EXPERIMENT):
    manifest_path = experiment / "build" / (NAME + ".build.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected = {"RunName": NAME, "ClockHz": 151200000, "SampleCycles": 1210,
                "TimeoutCycles": 4536000000, "ConsoleDelayCycles": 0, "EnableM": 0}
    for field, value in expected.items():
        require(type(manifest.get(field)) is type(value) and manifest[field] == value,
                "Wrong scope configuration: " + field)
    original = experiment / "build" / (NAME + ".hex")
    require(Path(manifest["Hex"]).resolve() == original.resolve(), "Wrong scope firmware path")
    require(digest(original) == digest(firmware_path) == manifest["HexSha256"] == EXPECTED_HASH,
            "Wrong scope firmware hash")
    require(set(manifest["SourceHashes"]) == EXPECTED_SOURCES, "Incomplete scope source hashes")
    for relative, expected_hash in manifest["SourceHashes"].items():
        require(digest(experiment / relative) == expected_hash, "Scope source changed: " + relative)
    require(manifest["Toolchain"]["Target"] == "riscv32-unknown-elf", "Wrong scope toolchain")
    return {"application": "scope", "firmware_sha256": EXPECTED_HASH,
            "manifest_sha256": digest(manifest_path), "clock_hz": 151200000,
            "sample_cycles": 1210, "timeout_cycles": 4536000000,
            "hardware_validated": False}


