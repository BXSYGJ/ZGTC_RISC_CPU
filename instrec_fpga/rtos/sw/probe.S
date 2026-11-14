/* Two CPU-bound tasks execute this with distinct seeds. No yield/delay occurs
 * in the loop: only timer preemption lets both make progress. s-registers and
 * caller-clobbered t3..t6 remain live across arbitrary timer interrupts.
 */
.section .text.probe,"ax",@progbits
.option norvc
.global vRegisterProbe
vRegisterProbe:
    mv s0,a2
    mv s1,a0
    mv s2,a1
    addi s3,a2,3
    addi s4,a2,4
    addi s5,a2,5
    addi s6,a2,6
    addi s7,a2,7
    addi s8,a2,8
    addi s9,a2,9
    addi s10,a2,10
    addi s11,a2,11
    addi t3,a2,64
    addi t4,a2,80
    addi t5,a2,96
    addi t6,a2,112
1:  bne s0,a2,3f
    bne s1,a0,3f
    bne s2,a1,3f
    addi t0,a2,3
    bne s3,t0,3f
    addi t0,a2,4
    bne s4,t0,3f
    addi t0,a2,5
    bne s5,t0,3f
    addi t0,a2,6
    bne s6,t0,3f
    addi t0,a2,7
    bne s7,t0,3f
    addi t0,a2,8
    bne s8,t0,3f
    addi t0,a2,9
    bne s9,t0,3f
    addi t0,a2,10
    bne s10,t0,3f
    addi t0,a2,11
    bne s11,t0,3f
    addi t0,a2,64
    bne t3,t0,3f
    addi t0,a2,80
    bne t4,t0,3f
    addi t0,a2,96
    bne t5,t0,3f
    addi t0,a2,112
    bne t6,t0,3f
    lw t1,0(s1)
    addi t1,t1,1
    sw t1,0(s1)
    mul t2,t1,s0
    j 1b
3:  li t0,1
    sw t0,0(a1)
4:  wfi
    j 4b
