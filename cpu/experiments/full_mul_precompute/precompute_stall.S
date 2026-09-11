.option norvc
.option norelax
.section .text.init
.globl _start
_start:
    li ra,17
    li sp,5
    li t1,0x200
    nop
    nop
    nop
    sw ra,0(t1)
    mul gp,ra,sp
    mul tp,gp,sp
    addi ra,ra,1
    mul t0,ra,sp
    nop
    nop
    nop
    sw sp,0(t1)
    mul gp,ra,sp
    li t1,0x10000000
    li t2,1
    sw t2,0(t1)
finished:
    j finished

