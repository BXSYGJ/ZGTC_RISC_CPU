import argparse
from pathlib import Path


MASK = (1 << 32) - 1


def signed(value, width=32):
    return (value & ((1 << (width - 1)) - 1)) - (value & (1 << (width - 1)))


class Trap(Exception):
    def __init__(self, cause, value):
        self.cause = cause
        self.value = value & MASK


class Reference:
    def __init__(self, image, memory_bytes=16384):
        if type(memory_bytes) is not int or memory_bytes not in (16384, 32768) or len(image) > memory_bytes:
            raise ValueError("Invalid reference memory geometry or oversized image")
        self.memory = bytearray(image) + bytearray(memory_bytes - len(image))
        self.registers = [0] * 32
        self.pc = 0
        self.csrs = {0x300: 0x1800, 0x301: 0x40000100, 0x304: 0, 0x305: 0,
                     0x306: 0, 0x340: 0, 0x341: 0, 0x342: 0, 0x343: 0,
                     0xF11: 0, 0xF12: 0, 0xF13: 0, 0xF14: 0}
        self.timer_irq = False
        self.retired = 0
        self.instret = 0
        self.traps = 0
        self.success = False

    def fetch(self):
        if self.pc % 4:
            raise Trap(0, self.pc)
        if self.pc + 4 > len(self.memory):
            raise Trap(1, self.pc)
        return int.from_bytes(self.memory[self.pc:self.pc + 4], "little")

    def decode(self, instruction):
        opcode = instruction & 127
        destination = (instruction >> 7) & 31
        funct3 = (instruction >> 12) & 7
        source1 = (instruction >> 15) & 31
        source2 = (instruction >> 20) & 31
        funct7 = instruction >> 25
        operand_a = self.registers[source1]
        operand_b = self.registers[source2]
        immediate = signed(instruction >> 20, 12)
        result = None
        next_pc = (self.pc + 4) & MASK
        store = None
        csr_write = None
        returning = False
        if opcode == 0x37:
            result = instruction & 0xFFFFF000
        elif opcode == 0x17:
            result = self.pc + (instruction & 0xFFFFF000)
        elif opcode == 0x6F:
            offset = ((instruction >> 31) << 20) | (((instruction >> 12) & 255) << 12)
            offset |= ((instruction >> 20) & 1) << 11
            offset |= ((instruction >> 21) & 1023) << 1
            result = next_pc
            next_pc = (self.pc + signed(offset, 21)) & MASK
        elif opcode == 0x67 and funct3 == 0:
            result = next_pc
            next_pc = (operand_a + immediate) & 0xFFFFFFFE
        elif opcode == 0x63:
            offset = ((instruction >> 31) << 12) | (((instruction >> 7) & 1) << 11)
            offset |= ((instruction >> 25) & 63) << 5
            offset |= ((instruction >> 8) & 15) << 1
            conditions = {0: operand_a == operand_b, 1: operand_a != operand_b,
                          4: signed(operand_a) < signed(operand_b),
                          5: signed(operand_a) >= signed(operand_b),
                          6: operand_a < operand_b, 7: operand_a >= operand_b}
            if funct3 not in conditions:
                raise Trap(2, instruction)
            if conditions[funct3]:
                next_pc = (self.pc + signed(offset, 13)) & MASK
        elif opcode in (0x13, 0x33):
            operand_b = immediate & MASK if opcode == 0x13 else operand_b
            if opcode == 0x33 and not (funct7 == 0 or (funct7 == 32 and funct3 in (0, 5))):
                raise Trap(2, instruction)
            if opcode == 0x13 and ((funct3 == 1 and funct7 != 0) or (funct3 == 5 and funct7 not in (0, 32))):
                raise Trap(2, instruction)
            if funct3 == 0:
                result = operand_a - operand_b if opcode == 0x33 and funct7 == 32 else operand_a + operand_b
            elif funct3 == 1:
                result = operand_a << (operand_b & 31)
            elif funct3 == 2:
                result = int(signed(operand_a) < signed(operand_b))
            elif funct3 == 3:
                result = int(operand_a < operand_b)
            elif funct3 == 4:
                result = operand_a ^ operand_b
            elif funct3 == 5:
                result = signed(operand_a) >> (operand_b & 31) if funct7 == 32 else operand_a >> (operand_b & 31)
            elif funct3 == 6:
                result = operand_a | operand_b
            elif funct3 == 7:
                result = operand_a & operand_b
        elif opcode in (0x03, 0x23):
            if opcode == 0x23:
                immediate = signed(((instruction >> 25) << 5) | ((instruction >> 7) & 31), 12)
            valid_widths = (0, 1, 2, 4, 5) if opcode == 0x03 else (0, 1, 2)
            if funct3 not in valid_widths:
                raise Trap(2, instruction)
            size = 1 << (funct3 & 3)
            address = (operand_a + immediate) & MASK
            if address % size:
                raise Trap(4 if opcode == 0x03 else 6, address)
            mmio = opcode == 0x23 and address in (0x10000000, 0x10000004) and size == 4
            if address + size > len(self.memory) and not mmio:
                raise Trap(5 if opcode == 0x03 else 7, address)
            if opcode == 0x03:
                result = int.from_bytes(self.memory[address:address + size], "little", signed=funct3 < 4)
            else:
                store = address, size, operand_b & ((1 << (8 * size)) - 1)
        elif opcode == 0x0F and funct3 in (0, 1):
            pass
        elif opcode == 0x73:
            if funct3 in (1, 2, 3, 5, 6, 7):
                address = instruction >> 20
                write_intent = (funct3 & 3) == 1 or source1 != 0
                counter = address in (0xB02, 0xB82, 0xC02, 0xC82)
                if (address not in self.csrs and not counter) or (address >> 10 == 3 and write_intent):
                    raise Trap(2, instruction)
                result = ((self.instret >> (32 if address & 128 else 0)) & MASK) if counter else self.csrs[address]
                source = source1 if funct3 >= 5 else operand_a
                new_value = source if (funct3 & 3) == 1 else result | source if (funct3 & 3) == 2 else result & ~source
                if write_intent:
                    csr_write = address, new_value & MASK
            elif instruction == 0x00000073:
                raise Trap(11, 0)
            elif instruction == 0x00100073:
                raise Trap(3, self.pc)
            elif instruction == 0x30200073:
                next_pc = self.csrs[0x341]
                returning = True
            elif instruction == 0x10500073:
                pass
            else:
                raise Trap(2, instruction)
        else:
            raise Trap(2, instruction)
        if next_pc % 4:
            raise Trap(0, next_pc)
        return destination, None if result is None else result & MASK, next_pc, store, csr_write, returning

    def retire(self, fields):
        pc, instruction = (int(value, 16) for value in fields[:2])
        wrote, destination = (int(value) for value in fields[2:4])
        actual_data = int(fields[4], 16)
        assert pc == self.pc, f"PC: RTL {pc:08x}, reference {self.pc:08x}"
        assert instruction == self.fetch(), f"Instruction at {pc:08x} differs from reference memory"
        expected_rd, result, next_pc, store, csr_write, returning = self.decode(instruction)
        expected_write = result is not None and expected_rd != 0
        assert bool(wrote) == expected_write, f"Write enable mismatch at {pc:08x}"
        if expected_write:
            assert destination == expected_rd and actual_data == result, (
                f"Result at {pc:08x}: RTL x{destination}={actual_data:08x}, reference x{expected_rd}={result:08x}")
            self.registers[expected_rd] = result
        if store:
            address, size, value = store
            if address == 0x10000000:
                assert value == 0xCAFE0001, "Reference firmware reported failure"
                self.success = True
            elif address == 0x10000004:
                self.timer_irq = bool(value & 1)
            else:
                self.memory[address:address + size] = value.to_bytes(size, "little")
        if csr_write:
            address, value = csr_write
            if address == 0x300:
                value = (value & 0x88) | 0x1800
            elif address == 0x304:
                value &= 0x888
            elif address == 0x305:
                value = (value & ~3) | int(value & 3 == 1)
            elif address == 0x306:
                value &= 7
            elif address == 0x341:
                value &= ~3
            elif address == 0x301:
                value = 0x40000100
            elif address == 0xB02:
                self.instret = (self.instret & ~MASK) | value
            elif address == 0xB82:
                self.instret = (self.instret & MASK) | (value << 32)
            self.csrs[address] = value
        if returning:
            status = self.csrs[0x300]
            self.csrs[0x300] = (status & ~0x88) | ((status & 0x80) >> 4) | 0x80
        self.pc = next_pc
        self.retired += 1
        if not csr_write or csr_write[0] not in (0xB02, 0xB82):
            self.instret = (self.instret + 1) & ((1 << 64) - 1)

    def trap(self, fields):
        pc, cause, value = (int(field, 16) for field in fields)
        assert pc == self.pc, f"Trap PC: RTL {pc:08x}, reference {self.pc:08x}"
        if cause >> 31:
            assert cause == 0x80000007 and self.timer_irq and self.csrs[0x304] & 128 and self.csrs[0x300] & 8
            assert value == 0
        else:
            try:
                self.decode(self.fetch())
            except Trap as expected:
                assert (cause, value) == (expected.cause, expected.value), f"Trap differs at {pc:08x}"
            else:
                raise AssertionError(f"Unexpected trap at {pc:08x}")
        self.csrs[0x341] = pc & ~3
        self.csrs[0x342] = cause
        self.csrs[0x343] = value
        status = self.csrs[0x300]
        self.csrs[0x300] = (status & ~0x88) | ((status & 8) << 4)
        self.pc = self.csrs[0x305] & ~3
        if cause >> 31 and self.csrs[0x305] & 3 == 1:
            self.pc += 4 * (cause & 31)
        self.traps += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--memory", type=Path, required=True)
    parser.add_argument("--memory-bytes", type=int, choices=(16384, 32768), default=16384)
    args = parser.parse_args()
    reference = Reference(args.image.read_bytes(), memory_bytes=args.memory_bytes)
    for line_number, line in enumerate(args.trace.read_text(encoding="ascii").splitlines(), 1):
        fields = line.split()
        try:
            if fields[0] == "R":
                reference.retire(fields[1:])
            elif fields[0] == "T":
                reference.trap(fields[1:])
            else:
                raise AssertionError("Unknown event")
        except (AssertionError, Trap) as error:
            raise AssertionError(f"{args.trace.name}:{line_number}: {error}") from error
    assert reference.success and reference.traps == 13, "Trace is incomplete"
    memory_words = [line.strip() for line in args.memory.read_text(encoding="ascii").splitlines() if line.strip() and not line.startswith("//")]
    actual_memory = b"".join(int(word, 16).to_bytes(4, "little") for word in memory_words)
    assert actual_memory == reference.memory, "Final memory differs from independent reference"
    print(f"PASS reference retired={reference.retired} traps={reference.traps} memory_bytes={len(actual_memory)} file={args.trace.name}")


if __name__ == "__main__":
    main()
