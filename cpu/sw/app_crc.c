/* CRC32 — computes CRC-32 over a test message and prints hex result. */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))
#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)
#define GPIO_OUTPUT REG32(0x200u)
#define TX_READY 0x1u

static void putc(char c) { while ((UART_STATUS & TX_READY) == 0u) {} UART_DATA = (unsigned int)(unsigned char)c; }
static void puts(const char *s) { while (*s) { if (*s == '\n') putc('\r'); putc(*s++); } }

static void puthex(unsigned int v) {
    static const char h[17] = "0123456789abcdef";
    char b[9]; int i;
    for (i = 7; i >= 0; i--) { b[i] = h[v & 15]; v >>= 4; }
    b[8] = 0; puts(b);
}

void trap_handler(void) { for (;;) {} }

static unsigned int crc32(const char *msg) {
    unsigned int crc = 0xFFFFFFFFu;
    while (*msg) {
        unsigned int byte = (unsigned int)(unsigned char)*msg++;
        int bit;
        crc ^= byte;
        for (bit = 0; bit < 8; bit++) {
            if (crc & 1u) crc = (crc >> 1) ^ 0xEDB88320u;
            else crc >>= 1;
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

int main(void) {
    static const char *tests[] = {
        "hello",
        "The quick brown fox jumps over the lazy dog",
        "ZGTC RISC-V CPU on Pango FPGA",
        0
    };
    int idx;
    puts("=== CRC32 ===\n");
    for (idx = 0; tests[idx] != 0; idx++) {
        unsigned int c = crc32(tests[idx]);
        puts("\""); puts(tests[idx]); puts("\" -> ");
        puthex(c); putc('\n');
        GPIO_OUTPUT = (unsigned char)(c >> 24);
    }
    puts("DONE\n");
    for (;;) {}
}