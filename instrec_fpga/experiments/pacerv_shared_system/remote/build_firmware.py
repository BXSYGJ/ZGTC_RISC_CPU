"""Build RV32IMC test firmware using native tools or direct WSL exec (no shell)."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent

def linux_path(p: Path) -> str:
    p = p.resolve()
    return "/mnt/" + p.drive[0].lower() + "/" + "/".join(p.parts[1:])

def main() -> None:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gcc", default="")
    ap.add_argument("--distro", default="Ubuntu-22.04")
    ap.add_argument("--wsl-prefix", default="/home/bx/.local/zgtc-riscv32-10.2.0/bin/riscv32-unknown-elf-")
    args=ap.parse_args()
    out=HERE/"firmware"
    out.mkdir(exist_ok=True)
    gcc=args.gcc or shutil.which("riscv32-unknown-elf-gcc")
    if gcc:
        prefix=[]; compiler=gcc; objcopy=gcc.removesuffix("gcc.exe")+"objcopy.exe" if gcc.endswith(".exe") else gcc.removesuffix("gcc")+"objcopy"
        convert=lambda p:str(p.resolve())
    else:
        prefix=["wsl.exe","-d",args.distro,"--cd","/","--exec"]
        compiler=args.wsl_prefix+"gcc"; objcopy=args.wsl_prefix+"objcopy"; convert=linux_path
    elf=out/"remote_prog.elf"; binary=out/"remote_prog.bin"; disasm=out/"remote_prog.dis"
    command=prefix+[compiler,"-march=rv32imc","-mabi=ilp32","-O2","-msmall-data-limit=0","-ffreestanding","-fno-builtin","-nostdlib","-nostartfiles",
        "-Wl,--no-relax","-Wl,-T,"+convert(HERE/"link.ld"),"-Wl,-Map,"+convert(out/"remote_prog.map"),convert(HERE/"start.S"),convert(HERE/"shared_selftest.c"),"-o",convert(elf)]
    subprocess.run(command,check=True)
    subprocess.run(prefix+[objcopy,"-O","binary",convert(elf),convert(binary)],check=True)
    objdump=objcopy.replace("objcopy","objdump")
    result=subprocess.run(prefix+[objdump,"-d",convert(elf)],check=True,capture_output=True)
    disasm.write_bytes(result.stdout)
    raw=binary.read_bytes()
    if len(raw)>8192: raise RuntimeError("Firmware exceeds the 8 KiB ROM.")
    raw+=b"\x00"*((-len(raw))%4)
    words=[int.from_bytes(raw[i:i+4],"little") for i in range(0,len(raw),4)]
    words.extend([0x00000013]*(2048-len(words)))
    (out/"remote_prog.hex").write_text("".join(f"{word:08x}\n" for word in words),encoding="ascii")
    meta={"isa":"RV32IMC","compiler":compiler,"command":command,"bytes":len(raw),"sha256":hashlib.sha256(binary.read_bytes()).hexdigest()}
    (out/"BUILD.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(meta,indent=2))

if __name__=="__main__": main()
