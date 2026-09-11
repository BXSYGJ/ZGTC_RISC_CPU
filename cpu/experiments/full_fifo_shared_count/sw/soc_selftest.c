#include "platform.h"
static volatile u32 software_seen;
static volatile u32 timer_seen;
static volatile u32 external_seen;
static volatile u32 initialized_data = 0x13579bdfu;
static void fail(u32 reason) {
    GPIO_OUTPUT = 0xe0u | reason;
    STATUS_CODE = 0xdead0000u | reason;
    for (;;) { }
}
void trap_handler(void) {
    u32 cause;
    __asm__ volatile ("csrr %0, mcause" : "=r"(cause));
    if (cause == 0x80000003u) {
        SOFTWARE_IRQ = 0;
        software_seen++;
    } else if (cause == 0x80000007u) {
        COMPARE_HIGH = 0xffffffffu;
        timer_seen++;
    } else if (cause == 0x8000000bu) {
#if EXTERNAL_UART
        UART_CONTROL = 0;
#else
        GPIO_PENDING = 0xffu;
#endif
        external_seen++;
    } else {
        fail(1);
    }
}
int main(void) {
    if (software_seen || timer_seen || external_seen || initialized_data != 0x13579bdfu) fail(2);
    GPIO_OUTPUT = 0x5au;
    PERF_SNAPSHOT = 1;
    u32 captured_cycle = PERF_CYCLES_LOW;
    if (PERF_SNAPSHOT != 1 || captured_cycle == 0) fail(5);
    if ((PERF_CONFIG & 2u) ? (PERF_I_MISSES != 0 || PERF_I_HITS != 0 || PERF_D_MISSES != 0 || PERF_D_HITS != 0 || PERF_WRITEBACKS != 0) : PERF_I_MISSES == 0) fail(5);
    if (PERF_CYCLES_LOW != captured_cycle) fail(5);
    PERF_SNAPSHOT = 1;
    if (PERF_SNAPSHOT != 2 || PERF_CYCLES_LOW <= captured_cycle) fail(5);
    uart_puts("ZGTC RV32I\r\n");
    __asm__ volatile ("csrw mie, %0" :: "r"(0x888u) : "memory");
    __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
    SOFTWARE_IRQ = 1;
    while (!software_seen) { }
    COMPARE_HIGH = 0xffffffffu;
    COMPARE_LOW = TIME_LOW + 2000u;
    COMPARE_HIGH = 0;
    while (!timer_seen) { }
#if EXTERNAL_UART
    UART_CONTROL = 1;
#else
    GPIO_PENDING = 0xffu;
    GPIO_ENABLE = 1;
#endif
    STATUS_CODE = 0x100u;
    while (!external_seen) { }
    GPIO_ENABLE = 0;
    if (software_seen != 1 || timer_seen != 1 || external_seen != 1) fail(3);
    __asm__ volatile ("fence.i" ::: "memory");
    STATUS_CODE = 0x101u;
    while ((UART_STATUS & 4u) == 0) { }
    if (UART_DATA != 0xa5u) fail(4);
    uart_putc(0x5au);
    uart_puts("SOC PASS\r\n");
    while ((UART_STATUS & 2u) == 0) { }
    GPIO_OUTPUT = 0xa5u;
    STATUS_CODE = 0xcafe0001u;
    return 0;
}
