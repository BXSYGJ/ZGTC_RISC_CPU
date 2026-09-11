#include "platform.h"
static volatile u32 interrupt_count;
static volatile u32 last_pending;
static void hex32(u32 value) {
    for (u32 digit = 0; digit < 8; digit++) {
        u32 nibble = (value >> (28 - 4 * digit)) & 15u;
        uart_putc((unsigned char)(nibble < 10 ? '0' + nibble : 'a' + nibble - 10));
    }
}
void trap_handler(void) {
    u32 cause;
    __asm__ volatile ("csrr %0, mcause" : "=r"(cause));
    u32 pending = GPIO_PENDING & GPIO_ENABLE & 1u;
    if (cause != 0x8000000bu || pending != 1u) {
        STATUS_CODE = 0xdead0010u;
        GPIO_ENABLE = 0;
        __asm__ volatile ("csrw mie, zero" ::: "memory");
        for (;;) { }
    }
    GPIO_PENDING = 1;
    last_pending = pending;
    interrupt_count++;
    GPIO_OUTPUT = interrupt_count;
}
static void report(void) {
    __asm__ volatile ("csrci mstatus, 8" ::: "memory");
    u32 input = GPIO_INPUT;
    u32 count = interrupt_count;
    u32 pending = GPIO_PENDING & 1u;
    u32 last = last_pending;
    u32 enabled = GPIO_ENABLE;
    __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
    uart_puts("GPIO I="); hex32(input);
    uart_puts(" N="); hex32(count);
    uart_puts(" P="); hex32(pending);
    uart_puts(" L="); hex32(last);
    uart_puts(" E="); hex32(enabled);
    uart_puts("\r\n");
}
int main(void) {
    UART_CONTROL = 0;
    GPIO_ENABLE = 0;
    GPIO_PENDING = 0xffu;
    GPIO_OUTPUT = 0;
    __asm__ volatile ("csrw mie, %0" :: "r"(0x800u) : "memory");
    __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
    STATUS_CODE = 0x4700u;
    uart_puts("GPIO READY S=status A=arm D=disarm\r\n");
    for (;;) {
        if ((UART_STATUS & 4u) == 0) continue;
        u32 command = UART_DATA;
        if (command == '\r' || command == '\n') continue;
        if (command == 'S') {
            report();
        } else if (command == 'A') {
            __asm__ volatile ("csrci mstatus, 8" ::: "memory");
            if (GPIO_INPUT & 1u) {
                __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
                uart_puts("GPIO RELEASE KEY FIRST\r\n");
                continue;
            }
            GPIO_ENABLE = 0;
            GPIO_PENDING = 0xffu;
            interrupt_count = 0;
            last_pending = 0;
            GPIO_OUTPUT = 0;
            GPIO_ENABLE = 1;
            __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
            uart_puts("GPIO ARMED\r\n");
        } else if (command == 'D') {
            __asm__ volatile ("csrci mstatus, 8" ::: "memory");
            GPIO_ENABLE = 0;
            __asm__ volatile ("csrsi mstatus, 8" ::: "memory");
            uart_puts("GPIO DISARMED\r\n");
        } else {
            uart_puts("GPIO UNKNOWN\r\n");
        }
    }
}
