#ifndef ZGTC_RISCV_TEST_H
#define ZGTC_RISCV_TEST_H

#define TESTNUM gp
#define RVTEST_RV32U .option norvc; .option norelax;
#define RVTEST_RV64U RVTEST_RV32U
#define RVTEST_CODE_BEGIN \
    .section .text.init; .balign 4; .globl _start; \
_start: \
    li TESTNUM, 0; \
    la t0, isa_trap; \
    csrw mtvec, t0; \
    csrw mie, zero; \
    csrw mstatus, zero;
#define RVTEST_PASS \
    li t5, 0x10000000; li t6, 1; sw t6, 0(t5); \
991: j 991b;
#define RVTEST_FAIL \
    li t5, 0x10000004; sw TESTNUM, 0(t5); \
992: j 992b;
#define RVTEST_CODE_END \
    RVTEST_PASS \
    .balign 4; \
isa_trap: \
    csrr t6, mcause; li t5, 0x10000008; sw t6, 0(t5); \
993: j 993b;
#define RVTEST_DATA_BEGIN .balign 16; .globl begin_signature; begin_signature:
#define RVTEST_DATA_END .balign 16; .globl end_signature; end_signature:

#endif
