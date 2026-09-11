import json
from pathlib import Path

import audit_clock_inputs as inputs

ROOT = Path(__file__).resolve().parent
digest = inputs.digest
require = inputs.require
load = inputs.load
portable = inputs.parent_audit.portable


def validate_manifest(manifest, reference, name, hex_file):
    flags = ["-DCPU_CLOCK_HZ=153000000u" if flag == "-DCPU_CLOCK_HZ=151200000u" else flag for flag in reference["Flags"]]
    require(reference["Flags"].count("-DCPU_CLOCK_HZ=151200000u") == 1, "Wrong reference clock flags")
    require(portable(manifest["Hex"]) == portable(hex_file), "Wrong firmware image path")
    expected = dict(reference, ClockHz=153000000, Flags=flags, Hex=manifest["Hex"], RunName=name, HexSha256=digest(hex_file))
    require(manifest == expected, "Firmware changes more than its clock and output identity")


def audit_firmware():
    source_record = inputs.audit_inputs()
    results = []
    for iterations in (10, 6000):
        for validation in (False, True):
            delay = "_p2700000" if iterations == 6000 else ""
            old_name = "coremark_v" + str(int(validation)) + "_i" + str(iterations) + delay + "_f151200000_rv32gcc_rv32im_O3_unroll_relax"
            name = old_name.replace("f151200000", "f153000000")
            reference_path = inputs.FIRMWARE_PARENT / "build" / (old_name + ".build.json")
            reference = load(reference_path)
            build = ROOT / "build"
            stage = build / (name + "-evidence-complete")
            record = load(stage / "receipt.json")
            manifest_path = build / (name + ".build.json")
            manifest = load(manifest_path)
            elf, binary, hex_file = (build / (name + suffix) for suffix in (".elf", ".bin", ".hex"))
            validate_manifest(manifest, reference, name, hex_file)
            require(record["passed"] is True and record["source_hashes"] == source_record["firmware_sources"], "Incomplete firmware source binding")
            require(record["builder_sha256"] == digest(ROOT / "build_clock_firmware.py"), "Firmware builder changed")
            require(record["reference_manifest_sha256"] == digest(reference_path) and record["manifest_sha256"] == digest(manifest_path), "Firmware manifest binding differs")
            flags = manifest["Flags"]
            link_flag = reference["ExtraLinkFlags"]
            flag_string = '-DFLAGS_STR="' + " ".join(flags) + " " + link_flag + '"'
            sources = [ROOT / "build/coremark-upstream" / filename for filename in ("core_list_join.c", "core_main.c", "core_matrix.c", "core_state.c", "core_util.c")]
            sources += [ROOT / filename for filename in ("sw/start.S", "sw/coremark/core_portme.c", "sw/coremark/ee_printf.c")]
            prefix = reference["Toolchain"]["Prefix"]
            expected_compile = [prefix + "gcc", *flags, flag_string, link_flag, "-I", ROOT / "sw/coremark", "-I", ROOT / "build/coremark-upstream", "-T", ROOT / "sw/link_soc.ld", "-o", elf, *sources, "-lgcc"]
            require(record["compile_command"] == list(map(portable, expected_compile)), "Firmware compile command differs")
            require(record["objcopy_command"] == list(map(portable, [prefix + "objcopy", "-O", "binary", elf, binary])), "Firmware objcopy command differs")
            require(record["outputs"] == {path.name: digest(path) for path in (elf, binary, hex_file)}, "Firmware output binding differs")
            require((stage / "version.log").read_text().strip() == "10.2.0" and (stage / "target.log").read_text().strip() == "riscv32-unknown-elf", "Wrong compiler logs")
            require(not (stage / "compile.log").read_text().strip() and not (stage / "objcopy.log").read_text().strip(), "Firmware compiler warning or error")
            image = binary.read_bytes()
            require(len(image) <= 65536, "Firmware too large")
            words = hex_file.read_text(encoding="ascii").splitlines()
            require(len(words) == 16384 and all(len(word) == 8 for word in words), "Wrong hexadecimal image geometry")
            require(b"".join(int(word, 16).to_bytes(4, "little") for word in words) == image + bytes(65536 - len(image)), "Binary and HEX differ")
            results.append({"name": name, "manifest_sha256": digest(manifest_path), "hex_sha256": digest(hex_file), "receipt_sha256": digest(stage / "receipt.json")})
    return {"schema": 1, "passed": True, "scope": "four clock-only firmware builds, exact compiler commands and source/output bindings; not performance qualification", "firmwares": results}


if __name__ == "__main__":
    result = audit_firmware()
    (ROOT / "build/firmware-audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
