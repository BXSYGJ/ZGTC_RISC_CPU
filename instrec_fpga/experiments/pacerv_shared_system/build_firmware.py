"""Build audio-control RV32IMC firmware via native GCC or direct WSL commands."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def linux_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) < 3 or resolved[1:3] != ":/":
        raise ValueError("Expected a Windows drive path: " + resolved)
    return "/mnt/" + resolved[0].lower() + resolved[2:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--distro", default="Ubuntu-22.04")
    ap.add_argument("--prefix", default=os.environ.get(
        "PACERV_GCC_PREFIX", "/home/bx/.local/zgtc-riscv32-10.2.0/bin/riscv32-unknown-elf-"))
    ap.add_argument("--legacy", action="store_true", help="build unchanged main.c as RV32I")
    args = ap.parse_args()
    out = ROOT / "build/pacerv_shared_system/firmware" / ("legacy" if args.legacy else "imc")
    out.mkdir(parents=True, exist_ok=True)
    records = []
    wsl = args.prefix.startswith("/")
    def file_arg(path: Path) -> str:
        return linux_path(path) if wsl else str(path)
    def run(tool: str, values: list[str]) -> str:
        cmd = [args.prefix + tool] + values
        if wsl:
            cmd = ["wsl.exe", "-d", args.distro, "--cd", "/", "--exec"] + cmd
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120)
        records.append({"command": cmd, "exit_code": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout
    march = "rv32i" if args.legacy else "rv32imc"
    elf, binary = out / "prog.elf", out / "prog.bin"
    main_source = ROOT / "sw/rv32" / ("main.c" if args.legacy else "main_pacerv.c")
    gcc = ["-march=" + march, "-mabi=ilp32", "-msmall-data-limit=0", "-std=c11",
           "-O2", "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-nostdlib",
           "-nostartfiles", "-Wl,--no-relax", "-Wl,-Map," + file_arg(out / "prog.map"),
           "-T", file_arg(ROOT / "sw/rv32/link.ld"), "-o", file_arg(elf),
           file_arg(ROOT / "sw/rv32/start.S"), file_arg(main_source), "-lgcc"]
    if not args.legacy:
        gcc.insert(0, "-DENABLE_M=1")
    version = run("gcc", ["--version"]).splitlines()[0]
    run("gcc", gcc)
    run("objcopy", ["-O", "binary", file_arg(elf), file_arg(binary)])
    data = binary.read_bytes()
    if len(data) > 8192:
        raise RuntimeError("ROM overflow: " + str(len(data)))
    padded = data + bytes((-len(data)) % 4)
    words = [int.from_bytes(padded[n:n+4], "little") for n in range(0, len(padded), 4)]
    image = out / "prog.hex"
    image.write_text("".join(f"{word:08x}\n" for word in words), encoding="ascii")
    # Banked pair fetch has the same contents as the linear data-side ROM.
    (out / "prog_even.hex").write_text("".join(f"{word:08x}\n" for word in words[::2]), encoding="ascii")
    (out / "prog_odd.hex").write_text("".join(f"{word:08x}\n" for word in words[1::2]), encoding="ascii")
    (out / "prog.dis").write_text(run("objdump", ["-d", file_arg(elf)]), encoding="utf-8")
    doc = {"isa": march, "compiler": version, "binary_bytes": len(data),
           "binary_sha256": hashlib.sha256(data).hexdigest(), "commands": records}
    (out / "BUILD.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"FIRMWARE_OK isa={march} bytes={len(data)} hex={image}")


if __name__ == "__main__":
    main()
