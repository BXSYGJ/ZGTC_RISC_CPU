/* Minimal application for verifying the flash-boot flow.
 * Prints a banner over UART, blinks the LEDs, and echoes received UART bytes.
 * Linked at 0x1000 (link_soc.ld) and launched by the bootloader.
 */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))
#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)
#define GPIO_OUTPUT REG32(0x200u)
#define TX_READY 0x1u
#define RX_VALID 0x4u

static void putc(char c) {
    while ((UART_STATUS & TX_READY) == 0u) { }
    UART_DATA = (unsigned int)(unsigned char)c;
}

static void puts(const char *text) {
    while (*text != '\0') {
        if (*text == '\n') putc('\r');
        putc(*text++);
    }
}

/* Required by cpu/sw/start.S (unused while interrupts stay disabled). */
void trap_handler(void) {
    for (;;) { }
}

int main(void) {
    unsigned int lfsr = 1u;
    unsigned int tick = 0u;
    puts("HELLO RV32 FROM 0x1000\n");
    for (;;) {
        tick++;
        if ((tick & 0x001fffffu) == 0u) {
            GPIO_OUTPUT = lfsr & 0xffu;
            lfsr = (lfsr >> 1) ^ ((lfsr & 1u) ? 0xb400u : 0u);
        }
        if ((UART_STATUS & RX_VALID) != 0u) {
            char received = (char)(UART_DATA & 0xffu);
            putc(received);
        }
    }
}
