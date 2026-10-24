/* Interrupt-path diagnostic for the PG2L100H bring-up.
 * Prints a stage letter before each wait so a hang can be pinpointed:
 *   A start  B irqs enabled  C sw irq requested  D sw irq seen
 *   E timer armed           F timer irq seen    G ext irq armed
 *   H ext irq seen          then IRQ PROBE PASS
 * X/Y/Z mark the failing stage (hang with that letter as last output).
 */
#include "platform.h"

static volatile u32 software_seen, timer_seen, external_seen;

static void mark(char c) {
    uart_putc((unsigned char)c);
    uart_putc('\n');
}

void trap_handler(void) {
    u32 cause;
    __asm__ volatile ("csrr %0, mcause" : "=r" (cause));
    if (cause == 0x80000003u) {
        SOFTWARE_IRQ = 0;
        software_seen++;
    } else if (cause == 0x80000007u) {
        COMPARE_HIGH = 0xffffffffu;
        timer_seen++;
    } else if (cause == 0x8000000bu) {
        GPIO_PENDING = 0xffu;
        external_seen++;
    }
}

int main(void) {
    mark('A');
    __asm__ volatile ("csrw mie, %0" :: "r" (0x888u) : "memory");
    __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
    mark('B');
    SOFTWARE_IRQ = 1;
    mark('C');
    for (u32 i = 0; i < 20000000u && !software_seen; i++) { }
    if (!software_seen) { mark('X'); return 1; }
    mark('D');
    COMPARE_HIGH = 0xffffffffu;
    COMPARE_LOW = TIME_LOW + 2000u;
    COMPARE_HIGH = 0;
    mark('E');
    for (u32 i = 0; i < 20000000u && !timer_seen; i++) { }
    if (!timer_seen) { mark('Y'); return 1; }
    mark('F');
    // external IRQ path 1: UART RX (uart_control[0] && rx_fifo_valid)
    UART_CONTROL = 1;
    mark('G');
    while (!external_seen) { }   // any byte from the PC triggers this
    UART_CONTROL = 0;
    mark('U');
    // external IRQ path 2: KEY1 rising edge on gpio bit0
    uart_puts("press KEY1\n");
    GPIO_PENDING = 0xffu;        // clear latched edges
    GPIO_ENABLE = 1;
    external_seen = 0;
    while (!external_seen) { }
    GPIO_ENABLE = 0;
    mark('K');
    uart_puts("IRQ PROBE PASS\n");
    GPIO_OUTPUT = 0xa5u;
    return 0;
}
