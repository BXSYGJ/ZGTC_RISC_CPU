/* RAM-only research derivative of cpu/sw/boot/bootloader.c in
 * BXSYGJ/ZGTC_RISC_CPU, commit 08dbfa1b930f87981fe213367f3c25a4e4f4134a.
 * Keeps the R/length/256-byte-K protocol. Adds a RAM CRC32 receipt.
 * Upstream originals and license files remain in the inspection checkout.
 */
#include <stdint.h>
#define REG(a) (*(volatile uint32_t *)(a))
#define UART_DATA REG(0x10000100u)
#define UART_STATUS REG(0x10000104u)
#define APP_BASE 0x1000u
#define APP_LIMIT 0xc000u
static void putc_uart(char c) {
    while (!(UART_STATUS & 1u)) {}
    UART_DATA = (unsigned char)c;
}
static void puts_uart(const char *s) { while (*s) putc_uart(*s++); }
static unsigned char getc_uart(void) {
    while (!(UART_STATUS & 4u)) {}
    return (unsigned char)UART_DATA;
}
static void hex32(uint32_t value) {
    const char *digits = "0123456789abcdef";
    for (int i=28; i>=0; i-=4) putc_uart(digits[(value >> i) & 15u]);
}
static uint32_t ram_crc32(uint32_t length) {
    volatile const unsigned char *p = (volatile const unsigned char *)APP_BASE;
    uint32_t crc = 0xffffffffu;
    for (uint32_t i=0; i<length; ++i) {
        crc ^= p[i];
        for (unsigned b=0; b<8; ++b) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
void main_boot(void) {
    REG(0x10000108u) = 0;
    puts_uart("ZBOOT RAM v26\n");
    for (;;) {
        unsigned char command = getc_uart();
        if (command == '?') { puts_uart("ZBOOT READY R\n"); continue; }
        if (command != 'R') { puts_uart("ERR command\n"); continue; }
        uint32_t length = 0;
        for (unsigned shift=0; shift<32; shift+=8) length |= (uint32_t)getc_uart() << shift;
        if (!length || length > APP_LIMIT-APP_BASE) { puts_uart("ERR length\n"); continue; }
        volatile unsigned char *destination = (volatile unsigned char *)APP_BASE;
        for (uint32_t i=0; i<length; ++i) {
            destination[i] = getc_uart();
            if ((i & 255u) == 255u) putc_uart('K');
        }
        putc_uart('K');
        __asm__ volatile("fence.i" ::: "memory");
        uint32_t crc = ram_crc32(length);
        puts_uart("\nBOOT CRC32="); hex32(crc); puts_uart(" bytes=0x"); hex32(length); putc_uart('\n');
        while (!(UART_STATUS & 2u)) {}
        __asm__ volatile("fence.i" ::: "memory");
        ((void (*)(void))APP_BASE)();
        puts_uart("ERR application returned\n");
        for (;;) {}
    }
}
