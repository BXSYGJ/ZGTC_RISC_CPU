.option norvc
.option norelax
.section .text.init
.globl _start
_start:
    la t0, handler
    csrw mtvec, t0
    li t0, 0x800
    csrw mie, t0
    li t0, 8
    csrw mstatus, t0
    li s0, 0
    li t0, 17
    li t1, 5
.globl target_div
target_div:
    div s1, t0, t1
    addi s2, s1, 7
    li t2, 10
    bne s2, t2, fail
    beq zero, zero, after_wrong_path
    div s1, zero, zero
    j fail
after_wrong_path:
.globl target_mul
target_mul:
    mul s3, t0, t1
    addi s4, s3, 1
    li t2, 86
    bne s4, t2, fail
    li t0, 0x80000001
    li t1, 3
.globl target_mulh
target_mulh:
    mulh s5, t0, t1
    li t2, -2
    bne s5, t2, fail
    li t2, 1
    bne s0, t2, fail
    csrr t0, misa
    li t1, 0x40001100
    bne t0, t1, fail
    li t0, 0x10000000
    li t1, 0xcafe0001
    sw t1, 0(t0)
finished:
    j finished
handler:
    addi s0, s0, 1
    mret
fail:
    li t0, 0x10000000
    li t1, 0xdead0001
    sw t1, 0(t0)
    j fail
