.section .text.start
.globl _start
.option norvc
.option push
.option norelax
_start:
    la sp, __stack_top
    la t0, __bss_start
    la t1, __bss_end
1:  bgeu t0, t1, 2f
    sw zero, 0(t0)
    addi t0, t0, 4
    j 1b
2:  jal main_boot
3:  j 3b
.option pop
