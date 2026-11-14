"""Run precise IRQ/CSR/RVC and 32 KiB ROM boundary tests on the frozen core."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "build/rtos/irq_precision"


class Image:
    def __init__(self):
        self.data = bytearray()
        self.labels = {}
        self.fixups = []

    def emit(self, word):
        self.data.extend(struct.pack("<I", word & 0xffffffff))

    def half(self, word):
        self.data.extend(struct.pack("<H", word))

    def mark(self, name):
        self.labels[name] = len(self.data)

    def org(self, address):
        if len(self.data) > address:
            raise ValueError("overlapping image sections")
        self.data.extend(bytes(address - len(self.data)))

    def li(self, rd, value):
        value &= 0xffffffff
        hi = ((value + 0x800) >> 12) & 0xfffff
        lo = value & 0xfff
        if lo >= 0x800:
            lo -= 0x1000
        if hi:
            self.emit((hi << 12) | (rd << 7) | 0x37)
            self.addi(rd, rd, lo)
        else:
            self.addi(rd, 0, lo)

    def addi(self, rd, rs, immediate):
        self.emit(((immediate & 0xfff) << 20) | (rs << 15) | (rd << 7) | 0x13)

    def csr(self, rd, address, rs=0, funct=2):
        self.emit((address << 20) | (rs << 15) | (funct << 12) | (rd << 7) | 0x73)

    def store(self, rs, base, offset):
        immediate = offset & 0xfff
        self.emit(((immediate >> 5) << 25) | (rs << 20) | (base << 15) |
                  (2 << 12) | ((immediate & 31) << 7) | 0x23)

    def jump(self, address):
        delta = address - len(self.data)
        imm = delta & 0x1fffff
        self.emit(((imm >> 20) << 31) | (((imm >> 1) & 0x3ff) << 21) |
                  (((imm >> 11) & 1) << 20) | (((imm >> 12) & 0xff) << 12) | 0x6f)

    def save(self, name):
        self.org(32768)
        path = OUT / (name + ".hex")
        path.write_text("".join(f"{int.from_bytes(self.data[i:i+4], 'little'):08x}\n"
                                for i in range(0, len(self.data), 4)), encoding="ascii")
        return path


def images():
    code = Image()
    code.li(2, 0x20004000)
    code.li(5, 0x80000000)
    code.li(6, 0x200)
    code.csr(0, 0x305, 6, 1)  # mtvec
    code.li(7, 0x13579135)
    code.csr(0, 0x340, 7, 1)
    code.csr(27, 0x340)
    code.li(7, 0x55)
    code.csr(0, 0x340, 7, 3)
    code.csr(26, 0x340)
    code.li(6, 0x80)
    code.csr(0, 0x304, 6, 1)
    code.csr(25, 0x304)
    code.li(6, 1000)
    code.store(6, 5, 0x38)
    code.store(0, 5, 0x3c)
    code.li(6, 8)
    code.csr(0, 0x300, 6, 2)
    code.li(8, 0x40000000)
    code.li(18, 10)
    while len(code.data) % 4 != 2:
        code.half(0x0001)
    code.mark("ddr_load")
    code.emit((8 << 15) | (2 << 12) | (10 << 7) | 3)  # lw a0,0(s0)
    code.mark("after_load")
    code.half(0x0905)  # c.addi s2,1 at a halfword PC
    code.csr(23, 0x300)
    code.li(6, 0xa5)
    code.store(6, 5, 0x14)
    code.jump(len(code.data))
    code.org(0x200)
    code.csr(20, 0x342)
    code.csr(21, 0x341)
    code.csr(22, 0x300)
    code.li(28, 0x80000000)
    code.li(29, 0xffffffff)
    code.store(29, 28, 0x3c)
    code.li(30, 1)
    code.emit(0x30200073)  # mret
    labels = dict(code.labels)
    code.save("irq")

    edge = Image()
    edge.li(5, 0x100)
    edge.csr(0, 0x305, 5, 1)
    edge.jump(0x7ff8)
    edge.org(0x100)
    edge.csr(20, 0x342)
    edge.csr(21, 0x341)
    edge.li(5, 0x80000000)
    edge.li(6, 0xa5)
    edge.store(6, 5, 0x14)
    edge.jump(len(edge.data))
    edge.org(0x7ff8)
    edge.half(0x4505)  # c.li a0,1
    edge.addi(11, 0, 17)  # 32-bit instruction straddling the last word
    edge.half(0x0585)  # c.addi a1,1 at 0x7ffe
    edge.save("rom_edge")
    (OUT / "IMAGE_LABELS.json").write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")
    return labels


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    iv, vvp = shutil.which("iverilog"), shutil.which("vvp")
    if not iv or not vvp:
        raise RuntimeError("Native Icarus Verilog is required")
    labels = images()
    rtl = [ROOT / "rtos/rtl/machine_timer.v", ROOT / "rtos/rtl/rv32_cpu_subsys.sv"]
    rtl += sorted((ROOT / "rtos/baseline125/src/cpu/vendor/pacerv_h3").glob("*.sv"))
    report = {"passed": False, "labels": labels, "commands": [], "sources": {}}
    for path in [HERE / "tb_irq_precision.sv", *rtl]:
        report["sources"][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        for name, top, token in [("irq", "tb_irq_precision", "IRQ_PRECISION_PASS"),
                                 ("rom_edge", "tb_rom_boundary", "ROM_BOUNDARY_PASS")]:
            target = OUT / (name + ".vvp")
            commands = [[iv, "-g2012", "-s", top, "-o", str(target),
                         "-DIRQ_RESUME_PC=" + str(labels["after_load"]),
                         str(HERE / "tb_irq_precision.sv"), *map(str, rtl)],
                        [vvp, "-i", str(target)]]
            for index, command in enumerate(commands):
                proc = subprocess.run(command, cwd=ROOT, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace", timeout=60)
                output = proc.stdout + proc.stderr
                report["commands"].append({"command": command, "cwd": str(ROOT),
                                            "exit_code": proc.returncode, "output": output})
                (OUT / (name + (".compile.log" if index == 0 else ".log"))).write_text(output, encoding="utf-8")
                if proc.returncode or (index == 1 and token not in output):
                    raise RuntimeError(output)
                if index == 1:
                    print(output, end="")
        report["passed"] = True
    finally:
        (OUT / "RESULTS.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RTOS_IRQ_PRECISION_TESTS_PASS cases=2")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
