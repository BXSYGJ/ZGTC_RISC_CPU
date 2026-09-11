import json
import subprocess
from pathlib import Path
from hashlib import sha256

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent / "full_mul_precompute_clock154285"


def digest(path):
    return sha256(path.read_bytes()).hexdigest().upper()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def command(arguments, log):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, timeout=180)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    require(result.returncode == 0 and not result.stderr.strip(), "Firmware command failed or warned: " + str(log))
    return result.stdout.strip()


def build(validation, iterations):
    source_record = load(ROOT / "source-inputs.json")
    for relative, checksum in source_record["firmware_sources"].items():
        require(digest(ROOT / relative) == checksum == digest(PARENT / relative), "Firmware source changed")
    delay = "_p2700000" if iterations == 6000 else ""
    old_name = "coremark_v" + str(int(validation)) + "_i" + str(iterations) + delay + "_f151200000_rv32gcc_rv32im_O3_unroll_relax"
    reference = load(PARENT / "build" / (old_name + ".build.json"))
    require(reference["ClockHz"] == 151200000 and reference["Iterations"] == iterations and reference["ValidationRun"] is validation, "Wrong reference firmware")
    require(reference["Toolchain"]["Version"] == "10.2.0" and reference["UpstreamRevision"] == "1f483d5b8316753a742cbf5590caf5bd0a4e4777", "Unexpected compiler or upstream")
    name = old_name.replace("f151200000", "f153000000")
    build_root = ROOT / "build"
    stage = build_root / (name + "-evidence-complete")
    stage.mkdir(exist_ok=False)
    prefix = reference["Toolchain"]["Prefix"]
    target = command([prefix + "gcc", "-dumpmachine"], stage / "target.log")
    version = command([prefix + "gcc", "-dumpversion"], stage / "version.log")
    require(target == reference["Toolchain"]["Target"] and version == "10.2.0", "Compiler identity differs")
    flags = list(reference["Flags"])
    require(flags.count("-DCPU_CLOCK_HZ=151200000u") == 1, "Clock flag missing or duplicated")
    flags[flags.index("-DCPU_CLOCK_HZ=151200000u")] = "-DCPU_CLOCK_HZ=153000000u"
    link_flag = reference["ExtraLinkFlags"]
    flag_string = '-DFLAGS_STR="' + " ".join(flags) + " " + link_flag + '"'
    sources = [ROOT / "build/coremark-upstream" / name for name in ("core_list_join.c", "core_main.c", "core_matrix.c", "core_state.c", "core_util.c")]
    sources += [ROOT / name for name in ("sw/start.S", "sw/coremark/core_portme.c", "sw/coremark/ee_printf.c")]
    elf = build_root / (name + ".elf")
    binary = build_root / (name + ".bin")
    hex_file = build_root / (name + ".hex")
    require(not any(path.exists() for path in (elf, binary, hex_file)), "Firmware output already exists")
    compile_command = [prefix + "gcc", *flags, flag_string, link_flag, "-I", ROOT / "sw/coremark", "-I", ROOT / "build/coremark-upstream",
                       "-T", ROOT / "sw/link_soc.ld", "-o", elf, *sources, "-lgcc"]
    command(compile_command, stage / "compile.log")
    objcopy_command = [prefix + "objcopy", "-O", "binary", elf, binary]
    command(objcopy_command, stage / "objcopy.log")
    image = binary.read_bytes()
    require(len(image) <= 65536, "Firmware exceeds 64 KiB")
    image += bytes(65536 - len(image))
    hex_file.write_text("\n".join(format(int.from_bytes(image[offset:offset + 4], "little"), "08x") for offset in range(0, 65536, 4)) + "\n", encoding="ascii")
    manifest = dict(reference, ClockHz=153000000, Flags=flags, Hex=str(hex_file), RunName=name, HexSha256=digest(hex_file))
    manifest_path = build_root / (name + ".build.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for relative, checksum in source_record["firmware_sources"].items():
        require(digest(ROOT / relative) == checksum == digest(PARENT / relative), "Firmware source changed during compilation")
    receipt = {"schema": 1, "scope": "same compiler, sources and options except CPU clock; no score claim", "passed": True,
               "reference_manifest_sha256": digest(PARENT / "build" / (old_name + ".build.json")), "builder_sha256": digest(Path(__file__)),
               "source_hashes": source_record["firmware_sources"], "compile_command": list(map(str, compile_command)),
               "objcopy_command": list(map(str, objcopy_command)), "manifest_sha256": digest(manifest_path),
               "outputs": {path.name: digest(path) for path in (elf, binary, hex_file)}}
    (stage / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("PASS clock-only firmware build: " + name, flush=True)


if __name__ == "__main__":
    for count in (10, 6000):
        for validation_run in (False, True):
            build(validation_run, count)
