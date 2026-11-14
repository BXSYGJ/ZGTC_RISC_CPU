#include "hal.h"
#include <stddef.h>

uint64_t ullMachineTime(void) {
    uint32_t hi, lo, again;
    do { hi = MTIME_HI; lo = MTIME_LO; again = MTIME_HI; } while (hi != again);
    return ((uint64_t)hi << 32) | lo;
}

void vMachineCompare(uint64_t value) {
    /* RV32 safe update: suppress a transient match while writing both halves. */
    MTIMECMP_HI = UINT32_MAX;
    MTIMECMP_LO = (uint32_t)value;
    MTIMECMP_HI = (uint32_t)(value >> 32);
}

static void vUartByte(char byte) {
    while ((UART_ST & 1u) == 0u) { }
    UART_TX = (uint32_t)(unsigned char)byte;
}

void vUartText(const char *text) { while (*text) vUartByte(*text++); }

void vUartDecimal(uint32_t value) {
    char digits[10];
    unsigned count = 0;
    do { digits[count++] = (char)('0' + value % 10u); value /= 10u; } while (value);
    while (count) vUartByte(digits[--count]);
}

void vUartHex(uint32_t value) {
    int shift;
    vUartText("0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        uint32_t digit = (value >> (unsigned)shift) & 15u;
        vUartByte((char)(digit < 10u ? '0' + digit : 'a' + digit - 10u));
    }
}

void vApplicationFatal(uint32_t code, uint32_t detail) {
    __asm__ volatile("csrci mstatus,8" ::: "memory");
    LED_REG = 0xeeu;
    vUartText("\r\nRTOS FATAL code="); vUartHex(code);
    vUartText(" detail="); vUartHex(detail); vUartText("\r\n");
    for (;;) __asm__ volatile("wfi");
}

void *memset(void *destination, int byte, size_t count) {
    unsigned char *out = destination;
    while (count--) *out++ = (unsigned char)byte;
    return destination;
}

void *memcpy(void *destination, const void *source, size_t count) {
    unsigned char *out = destination;
    const unsigned char *in = source;
    while (count--) *out++ = *in++;
    return destination;
}

int memcmp(const void *left, const void *right, size_t count) {
    const unsigned char *a = left, *b = right;
    while (count--) { if (*a != *b) return (int)*a - (int)*b; ++a; ++b; }
    return 0;
}
