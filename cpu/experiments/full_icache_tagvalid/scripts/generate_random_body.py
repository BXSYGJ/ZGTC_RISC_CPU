import argparse
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument("--count", type=int, default=256)
    args = parser.parse_args()
    if not 1 <= args.count <= 320:
        raise ValueError("Instruction count must fit the self-test text region")
    generator = random.Random(args.seed)
    registers = ["t0", "t1", "t2", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "s1", "s2", "s3", "s4", "s5", "s6"]
    lines = ["    li s0, 0x2000"]
    lines += [f"    li {register}, 0x{generator.getrandbits(32):08x}" for register in registers]
    register_ops = ["add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and"]
    immediate_ops = ["addi", "slti", "sltiu", "xori", "ori", "andi"]
    for index in range(args.count):
        destination, source1, source2 = generator.choices(registers, k=3)
        choice = generator.randrange(6)
        if choice == 0:
            lines.append(f"    {generator.choice(register_ops)} {destination}, {source1}, {source2}")
        elif choice == 1:
            lines.append(f"    {generator.choice(immediate_ops)} {destination}, {source1}, {generator.randrange(-2048, 2048)}")
        elif choice == 2:
            lines.append(f"    {generator.choice(['slli', 'srli', 'srai'])} {destination}, {source1}, {generator.randrange(32)}")
        elif choice in (3, 4):
            operation = generator.choice(["lb", "lh", "lw", "lbu", "lhu"] if choice == 3 else ["sb", "sh", "sw"])
            size = 4 if operation.endswith("w") else 2 if "h" in operation else 1
            offset = generator.randrange(16, 256) & -size
            lines.append(f"    {operation} {destination}, {offset}(s0)")
        else:
            label = f"random_forward_{index}"
            operation = generator.choice(["beq", "bne", "blt", "bge", "bltu", "bgeu"])
            lines += [f"    {operation} {source1}, {source2}, {label}", f"    addi {destination}, {source1}, 1", f"{label}:"]
    args.destination.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(f"Generated random instruction body: seed={args.seed} operations={args.count}")


if __name__ == "__main__":
    main()
