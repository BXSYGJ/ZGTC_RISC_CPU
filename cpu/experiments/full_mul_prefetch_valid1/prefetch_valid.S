.option norvc
.option norelax
.section .text.init
.globl _start
_start:
    li x1,7
    li x2,9
    nop
    nop
    nop
    nop
    nop
    mul x3,x1,x2
    nop
    nop
    nop
    nop
    nop
    mul x4,x0,x1
    nop
    nop
    nop
    nop
    nop
    mul x5,x6,x1
    nop
    nop
    nop
    nop
    nop
    mul x7,x1,x8
    nop
    nop
    nop
    nop
    nop
    li x6,11
    mul x9,x6,x2
    nop
    nop
    nop
    nop
    nop
    li x10,13
    mul x11,x10,x2
    nop
    nop
    nop
    nop
    nop
    li x13,0
    nop
    nop
    nop
    nop
    nop
    mul x14,x13,x2
    li x31,0x10000000
    sw x1,0(x31)
finished:
    j finished
