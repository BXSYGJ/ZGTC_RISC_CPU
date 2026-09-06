.section .text
.globl _start
.option norvc
.macro CHECK register, value
    li s7, \value
    bne \register, s7, fail
.endm
.macro EXPECT cause, value
    li s8, \cause
    li s9, \value
.endm
_start:
    la t0, trap_handler
    csrw mtvec, t0
    li s11, 0
    li sp, 0x3ff0
    li t0, 5
    addi t1, t0, -8
    add t2, t0, t1
    CHECK t2, 2
    sub s0, t1, t0
    CHECK s0, -8
    sll s1, t0, t0
    CHECK s1, 160
    slt s1, t1, t0
    CHECK s1, 1
    sltu s1, t1, t0
    CHECK s1, 0
    xor s1, t0, t1
    CHECK s1, -8
    or s1, t0, t1
    CHECK s1, -3
    and s1, t0, t1
    CHECK s1, 5
    srl s1, t1, t0
    CHECK s1, 0x07ffffff
    sra s1, t1, t0
    CHECK s1, -1
    slti s1, t1, -2
    CHECK s1, 1
    sltiu s1, t0, -1
    CHECK s1, 1
    xori s1, t1, -1
    CHECK s1, 2
    ori s1, t0, 2
    CHECK s1, 7
    andi s1, t1, 255
    CHECK s1, 253
    slli s1, t0, 31
    CHECK s1, 0x80000000
    srli s1, s1, 31
    CHECK s1, 1
    srai s1, t1, 31
    CHECK s1, -1
    li s2, 32
    sll s1, t0, s2
    CHECK s1, 5
    addi zero, zero, 9
    CHECK zero, 0
    lui s1, 0x12345
    CHECK s1, 0x12345000
pc_check:
    auipc s1, 0
    la s2, pc_check
    bne s1, s2, fail
    beq t0, t0, 1f
    j fail
1:  bne t0, t1, 2f
    j fail
2:  blt t1, t0, 3f
    j fail
3:  bge t0, t1, 4f
    j fail
4:  bltu t0, t1, 5f
    j fail
5:  bgeu t1, t0, 6f
    j fail
6:  beq t0, t1, fail
    bne t0, t0, fail
    blt t0, t1, fail
    bge t1, t0, fail
    bltu t1, t0, fail
    bgeu t0, t1, fail
    jal ra, subroutine
after_call:
    CHECK a0, 42
    la s1, after_call
    bne ra, s1, fail
    li s0, 0x2000
    li s1, 0x112280ff
    sw s1, 0(s0)
    lw s2, 0(s0)
    add s3, s2, s2
    CHECK s3, 0x224501fe
    lb s2, 0(s0)
    CHECK s2, -1
    lbu s2, 0(s0)
    CHECK s2, 255
    lh s2, 0(s0)
    CHECK s2, -32513
    lhu s2, 0(s0)
    CHECK s2, 33023
    lb s2, 1(s0)
    CHECK s2, -128
    lhu s2, 2(s0)
    CHECK s2, 4386
    li s1, 0xaa
    sb s1, 1(s0)
    li s1, 0xbeef
    sh s1, 2(s0)
    lw s2, 0(s0)
    CHECK s2, 0xbeefaaff
    sw s2, 4(s0)
    lw s3, 4(s0)
    bne s2, s3, fail
    li s4, 24
    li s5, 0
loop:
    add s5, s5, s4
    addi s4, s4, -1
    bne s4, zero, loop
    CHECK s5, 300
    li s1, 0x10000000
    j safe_path
    sw zero, 0(s1)
safe_path:
#include "random_body.inc"
    li t0, 0x1234
    csrrw t1, mscratch, t0
    CHECK t1, 0
    csrrs t1, mscratch, zero
    CHECK t1, 0x1234
    csrrsi t1, mscratch, 3
    CHECK t1, 0x1234
    csrrci t1, mscratch, 7
    CHECK t1, 0x1237
    csrrwi t1, mscratch, 31
    CHECK t1, 0x1230
    li t0, 32
    csrrs t1, mscratch, t0
    CHECK t1, 31
    csrrc t1, mscratch, t0
    CHECK t1, 63
    csrr t1, mscratch
    CHECK t1, 31
    csrw minstret, zero
    csrr t1, minstret
    CHECK t1, 0
    EXPECT 4, 0x2001
    lh s1, 1(s0)
    EXPECT 6, 0x2001
    sh s1, 1(s0)
    EXPECT 4, 0x2002
    lw s1, 2(s0)
    EXPECT 6, 0x2002
    sw s1, 2(s0)
    EXPECT 2, 0x02000033
    .word 0x02000033
    EXPECT 2, 0xc0001073
    .word 0xc0001073
    EXPECT 11, 0
    ecall
    li s8, 3
    la s9, breakpoint_site
breakpoint_site:
    ebreak
    EXPECT 0, 2
    li t0, 2
    jalr zero, 0(t0)
    EXPECT 5, 0x8000
    li t0, 0x8000
    lw s1, 0(t0)
    EXPECT 7, 0x8000
    sw s1, 0(t0)
    EXPECT 1, 0x8000
    la s10, after_instruction_fault
    jalr zero, 0(t0)
after_instruction_fault:
    CHECK s11, 12
    fence
    fence.i
    jal ra, mutable_function
    CHECK a0, 7
    la t0, mutable_function
    li t1, 0x00900513
    sw t1, 0(t0)
    fence.i
    jal ra, mutable_function
    CHECK a0, 9
    EXPECT 0x80000007, 0
    li t0, 128
    csrw mie, t0
    csrsi mstatus, 8
    li t0, 0x10000004
    li t1, 1
    sw t1, 0(t0)
wait_interrupt:
    li t2, 13
    bne s11, t2, wait_interrupt
    csrci mstatus, 8
    li t0, 0x10000000
    li t1, 0xcafe0001
    sw t1, 0(t0)
finished:
    j finished
mutable_function:
    addi a0, zero, 7
    jalr zero, 0(ra)
subroutine:
    li a0, 42
    jalr zero, 0(ra)
trap_handler:
    csrr t3, mcause
    bne t3, s8, fail
    csrr t4, mtval
    bne t4, s9, fail
    addi s11, s11, 1
    blt t3, zero, interrupt_handler
    li t4, 1
    beq t3, t4, instruction_fault_handler
    csrr t4, mepc
    addi t4, t4, 4
    csrw mepc, t4
    mret
instruction_fault_handler:
    csrw mepc, s10
    mret
interrupt_handler:
    li t4, 0x10000004
    sw zero, 0(t4)
    mret
fail:
    li t0, 0x10000000
    li t1, 0xdead0001
    sw t1, 0(t0)
    j fail
