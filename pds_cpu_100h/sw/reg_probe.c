/* Register-level diagnostic for the external-interrupt path on PG2L100H.
 * Prints the actual MMIO/CSR state so the failing stage is visible:
 *   CTRL   UART_CONTROL readback after writing 1
 *   STAT   UART_STATUS before the byte (bit2 = rx_fifo_valid)
 *   STAT2  UART_STATUS after the byte
 *   DATA   UART_DATA readback (the byte itself)
 *   T:<hex> mcause of every trap that occurs (flood = re-triggering)
 */
#include "platform.h"

static volatile u32 software_seen, timer_seen, external_seen;
static volatile u32 trap_count;

static void puthex(u32 v) {
    const char *h = "0123456789abcdef";
    for (int i = 7; i >= 0; i--) uart_putc((unsigned char)h[(v >> (i * 4)) & 0xf]);
}

void trap_handler(void) {
    u32 cause;
    __asm__ volatile ("csrr %0, mcause" : "=r" (cause));
    trap_count++;
    uart_puts("T:");
    puthex(cause);
    uart_puts("\n");
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
    uart_puts("REGPROBE\n");
    __asm__ volatile ("csrw mie, %0" :: "r" (0x888u) : "memory");
    __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
    SOFTWARE_IRQ = 1;
    while (!software_seen) { }
    uart_puts("SW OK\n");
    COMPARE_HIGH = 0xffffffffu;
    COMPARE_LOW = TIME_LOW + 2000u;
    COMPARE_HIGH = 0;
    while (!timer_seen) { }
    uart_puts("TMR OK\n");

    UART_CONTROL = 1;
    uart_puts("CTRL=");
    puthex(UART_CONTROL);
    uart_puts("\n");
    uart_puts("STAT=");
    puthex(UART_STATUS);
    uart_puts("\n");
    uart_puts("SEND BYTE NOW\n");
    /* wait up to ~2 s for a byte in the RX fifo (bit2 of UART_STATUS) */
    for (u32 i = 0; i < 60000000u && !(UART_STATUS & 4u); i++) { }
    uart_puts("STAT2=");
    puthex(UART_STATUS);
    uart_puts("\n");
    if (UART_STATUS & 4u) {
        uart_puts("DATA=");
        puthex(UART_DATA);
        uart_puts("\n");
    }
    uart_puts("EXT=");
    puthex(external_seen);
    uart_puts(" TRAPS=");
    puthex(trap_count);
    uart_puts("\n");
    GPIO_OUTPUT = 0xa5u;
    for (;;) { }
}
