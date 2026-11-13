"""Build the exact directed RV32IMC integration image without a cross compiler."""
from pathlib import Path
import json
import struct

HERE = Path(__file__).resolve().parent
image = bytearray()
labels = {}
fixups = []


def emit(word):
    image.extend(struct.pack('<I', word & 0xffffffff))


def half(word):
    image.extend(struct.pack('<H', word))


def label(name):
    labels[name] = len(image)


def lui(rd, value):
    emit((value & 0xfffff000) | (rd << 7) | 0x37)


def addi(rd, rs, imm):
    emit(((imm & 0xfff) << 20) | (rs << 15) | (rd << 7) | 0x13)


def li(rd, value):
    value &= 0xffffffff
    upper = ((value + 0x800) >> 12) & 0xfffff
    low = value & 0xfff
    low -= 0x1000 if low & 0x800 else 0
    if upper:
        lui(rd, upper << 12)
        addi(rd, rd, low)
    else:
        addi(rd, 0, low)


def branch(name, rs1, rs2, funct=1):
    fixups.append(('b', len(image), name, rs1, rs2, funct))
    emit(0)


def jump(name, rd=0):
    fixups.append(('j', len(image), name, rd))
    emit(0)


def addr(rd, name):
    fixups.append(('a', len(image), name, rd))
    emit(0)


def load(rd, base, offset=0, funct=2):
    emit(((offset & 0xfff) << 20) | (base << 15) | (funct << 12) | (rd << 7) | 3)


def store(rs, base, offset=0, funct=2):
    imm = offset & 0xfff
    emit(((imm >> 5) << 25) | (rs << 20) | (base << 15) |
         (funct << 12) | ((imm & 31) << 7) | 0x23)


def csr(rd, address, rs, funct=1):
    emit((address << 20) | (rs << 15) | (funct << 12) | (rd << 7) | 0x73)


def check(reg, expected, test):
    li(23, test)
    li(24, expected)
    branch('fail', reg, 24)


def mulop(funct, a, b, expected, test):
    li(5, a)
    li(6, b)
    emit((1 << 25) | (6 << 20) | (5 << 15) | (funct << 12) | (10 << 7) | 0x33)
    check(10, expected, test)


label('start')
half(0x0001)                 # c.nop: the next 32-bit instruction straddles words.
li(2, 0x20002000)
addr(5, 'trap')
csr(0, 0x305, 5)
li(20, 0)                    # trap count
half(0x451d)                 # c.li a0, 7
half(0x0505)                 # c.addi a0, 1
check(10, 8, 1)
mulop(0, 7, -3, -21, 2)     # MUL
mulop(1, -1, 2, -1, 3)      # MULH
mulop(2, -1, 2, -1, 4)      # MULHSU
mulop(3, 0xffffffff, 2, 1, 5)  # MULHU
mulop(4, 7, -3, -2, 6)      # DIV
mulop(5, 7, 3, 2, 7)        # DIVU
mulop(6, 7, -3, 1, 8)       # REM
mulop(7, 7, 3, 1, 9)        # REMU
mulop(4, 9, 0, -1, 10)
mulop(6, 9, 0, 9, 11)
mulop(4, 0x80000000, -1, 0x80000000, 12)
mulop(6, 0x80000000, -1, 0, 13)
li(16, 30)
li(17, 0)
label('loop')
half(0x0885)                 # c.addi a7, 1
addi(16, 16, -1)
branch('loop', 16, 0)
check(17, 30, 14)
jump('subroutine', 1)
check(17, 31, 15)
li(5, 0x76543210)
csr(0, 0x340, 5)
csr(10, 0x340, 0, 2)
check(10, 0x76543210, 16)
csr(10, 0xc00, 0, 2)
addi(0, 0, 0)
csr(11, 0xc00, 0, 2)
branch('fail', 10, 11, 0)
li(8, 0x20000000)
li(9, 0x12345678)
store(9, 8)
load(10, 8)
check(10, 0x12345678, 17)
li(8, 0x40000000)
li(9, 0x12345678)
store(9, 8)
load(10, 8)
check(10, 0x12345678, 18)
li(9, 0xa5)
store(9, 8, 1, 0)
load(10, 8)
check(10, 0x1234a578, 19)
load(10, 8, 1, 0)
check(10, -91, 20)
load(10, 8, 1, 4)
check(10, 0xa5, 21)
li(9, 0xbeef)
store(9, 8, 2, 1)
load(10, 8)
check(10, 0xbeefa578, 22)
load(10, 8, 2, 5)
check(10, 0xbeef, 23)
li(8, 0x41000000)
load(10, 8)
check(10, 0xdecafbad, 24)
store(9, 8)                 # observation alias store is rejected by bridge.
check(20, 1, 25)
emit(0x0000100f)            # fence.i after DDR completion
li(8, 0x80000024)
li(9, 1)
store(9, 8)                 # original NPU soft-start MMIO
li(8, 0x80000014)
li(9, 0xa5)
store(9, 8)
label('done')
jump('done')
label('subroutine')
half(0x0885)
half(0x8082)                 # c.jr ra
while len(image) % 4:
    half(0x0001)
label('trap')
csr(10, 0x342, 0, 2)
li(24, 7)
branch('fail', 10, 24)
csr(10, 0x343, 0, 2)
li(24, 0x41000000)
branch('fail', 10, 24)
addi(20, 20, 1)
csr(5, 0x341, 0, 2)
addi(5, 5, 4)
csr(0, 0x341, 5)
emit(0x30200073)
label('fail')
li(8, 0x80000014)
li(9, 0xee)
store(9, 8)
label('failed')
jump('failed')

for fix in fixups:
    kind, pc, name, *args = fix
    target = labels[name]
    if kind == 'a':
        rd, = args
        assert 0 <= target < 2048
        word = (target << 20) | (rd << 7) | 0x13
    elif kind == 'b':
        rs1, rs2, funct = args
        off = target - pc
        assert off % 2 == 0 and -4096 <= off < 4096
        word = (((off >> 12) & 1) << 31) | (((off >> 5) & 63) << 25)
        word |= (rs2 << 20) | (rs1 << 15) | (funct << 12)
        word |= (((off >> 1) & 15) << 8) | (((off >> 11) & 1) << 7) | 0x63
    else:
        rd, = args
        off = target - pc
        word = (((off >> 20) & 1) << 31) | (((off >> 1) & 1023) << 21)
        word |= (((off >> 11) & 1) << 20) | (((off >> 12) & 255) << 12)
        word |= (rd << 7) | 0x6f
    struct.pack_into('<I', image, pc, word)

assert len(image) <= 8192
used = len(image)
image.extend(bytes(8192 - len(image)))
out = HERE / 'pacerv_directed.hex'
out.write_text(''.join(f'{int.from_bytes(image[i:i+4], "little"):08x}\n'
                       for i in range(0, len(image), 4)), encoding='ascii')
(HERE / 'pacerv_directed_manifest.json').write_text(
    json.dumps({'used_bytes': used, 'labels': labels,
                'instruction_set': 'RV32IMC_Zicsr_Zifencei',
                'checks': 25, 'success_led': '0xa5', 'failure_led': '0xee'}, indent=2) + '\n',
    encoding='utf-8')
print(f'BUILT {out} used_bytes={used} checks=25')
