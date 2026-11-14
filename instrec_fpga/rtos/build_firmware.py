"""Build the 125 MHz InstRec FreeRTOS image with native LLVM or RISC-V GCC.

No WSL, shell command strings, external libc, or host execution is required.
Default output: instrec_fpga/build/rtos/firmware (test uses /test).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SW = HERE / "sw"
KERNEL = HERE / "vendor/FreeRTOS-Kernel"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gcc-prefix", help="Native prefix ending in riscv-none-elf- or equivalent")
    parser.add_argument("--llvm-bin", type=Path,
                        default=Path(os.environ.get("INSTREC_LLVM_BIN", "C:/Program Files/LLVM/bin")))
    args = parser.parse_args()
    default_out = ROOT / "build/rtos/firmware"
    if args.test:
        default_out = default_out / "test"
    out = args.output or default_out
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commands: list[dict] = []
    provenance_path = KERNEL / "PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance["tag"] != "V11.3.3" or provenance["commit"] != \
            "89592801dd8b73329a7583719b7e3567b50910e5":
        raise RuntimeError("Unexpected FreeRTOS source version")
    for entry in provenance["files"]:
        source = KERNEL / entry["path"]
        if sha256(source) != entry["sha256"]:
            raise RuntimeError("Frozen FreeRTOS source changed: " + str(source))

    def run(command: list[str | Path]) -> str:
        argv = [str(item) for item in command]
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=120,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        record = {"command": argv, "cwd": str(ROOT), "exit_code": result.returncode,
                  "stdout": result.stdout, "stderr": result.stderr}
        commands.append(record)
        if result.returncode:
            (out / "FAILED_COMMANDS.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    if args.gcc_prefix:
        compiler = args.gcc_prefix + "gcc"
        objcopy = args.gcc_prefix + "objcopy"
        objdump = args.gcc_prefix + "objdump"
        size = args.gcc_prefix + "size"
        target_flags: list[str] = []
        linker_flags: list[str] = []
    else:
        compiler = str(args.llvm_bin / "clang.exe")
        objcopy = str(args.llvm_bin / "llvm-objcopy.exe")
        objdump = str(args.llvm_bin / "llvm-objdump.exe")
        size = str(args.llvm_bin / "llvm-size.exe")
        for tool in (compiler, objcopy, objdump, size):
            if not Path(tool).is_file() and not shutil.which(tool):
                raise FileNotFoundError(tool)
        target_flags = ["--target=riscv32-unknown-elf"]
        linker_flags = ["-fuse-ld=lld"]
    compiler_version = run([compiler, "--version"]).splitlines()[0]
    sources = [SW / name for name in ("start.S", "portASM.S", "port.c", "main.c", "hal.c")]
    if args.test:
        sources.append(SW / "probe.S")
        sources.append(SW / "critical_test.c")
    sources.extend(KERNEL / name for name in ("tasks.c", "queue.c", "list.c"))
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
    common = target_flags + ["-march=rv32imc_zicsr_zifencei", "-mabi=ilp32",
        "-mcmodel=medlow", "-msmall-data-limit=0", "-Os", "-g", "-ffreestanding",
        "-fno-builtin", "-fno-stack-protector", "-ffunction-sections", "-fdata-sections",
        "-Wall", "-Wextra", "-Werror", "-I" + str(SW),
        "-I" + str(SW / "freestanding"), "-I" + str(KERNEL / "include"),
        "-DRTOS_TEST=" + str(int(args.test))]
    objects: list[Path] = []
    for number, source in enumerate(sources):
        obj = out / f"{number:02d}_{source.stem}.o"
        flags = [] if source.suffix == ".S" else ["-std=c11"]
        run([compiler, *common, *flags, "-c", source, "-o", obj])
        objects.append(obj)
    elf, binary = out / "prog.elf", out / "prog.bin"
    run([compiler, *target_flags, "-march=rv32imc_zicsr_zifencei", "-mabi=ilp32",
         *linker_flags, "-nostdlib", "-Wl,--gc-sections", "-Wl,--no-relax",
         "-Wl,-Map," + str(out / "prog.map"), "-T", SW / "link.ld",
         *objects, "-o", elf])
    run([objcopy, "-O", "binary", elf, binary])
    data = binary.read_bytes()
    if len(data) > 16384:
        raise RuntimeError("RTOS ROM exceeds 16 KiB")
    padded = data + bytes((-len(data)) % 4)
    words = [int.from_bytes(padded[i:i + 4], "little") for i in range(0, len(padded), 4)]
    for name, image in (("prog.hex", words), ("prog_even.hex", words[::2]),
                        ("prog_odd.hex", words[1::2])):
        (out / name).write_text("".join(f"{word:08x}\n" for word in image), encoding="ascii")
    (out / "prog.dis").write_text(run([objdump, "-d", elf]), encoding="utf-8")
    sizes = run([size, elf])
    (out / "SIZE.txt").write_text(sizes, encoding="utf-8")
    inputs = sorted(set(sources + list(SW.rglob("*.h")) + list((KERNEL / "include").rglob("*.h")) +
                        [SW / "link.ld", provenance_path, Path(__file__).resolve()]))
    report = {"kernel": "FreeRTOS-Kernel V11.3.3", "kernel_commit":
              "89592801dd8b73329a7583719b7e3567b50910e5", "compiler": compiler_version,
              "isa": "rv32imc_zicsr_zifencei", "cpu_clock_hz": 125000000,
              "tick_rate_hz": 1000, "test_image": args.test, "test_mode": args.test,
              "kernel_files_verified": len(provenance["files"]),
              "rom_capacity": 16384, "ram_capacity": 16384,
              "binary_bytes": len(data), "binary_sha256": sha256(binary),
              "sizes": sizes, "inputs": [{"path": str(p.relative_to(ROOT)),
                   "sha256": sha256(p)} for p in inputs], "commands": commands}
    (out / "BUILD.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(sizes.strip())
    print(f"RTOS_FIRMWARE_PASS test={int(args.test)} bytes={len(data)} hex={out / 'prog.hex'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
