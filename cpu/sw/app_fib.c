/* Fibonacci sequence — prints first 24 Fibonacci numbers in decimal. */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))
#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)
#define GPIO_OUTPUT REG32(0x200u)
#define TX_READY 0x1u

static void putc(char c) { while ((UART_STATUS & TX_READY) == 0u) {} UART_DATA = (unsigned int)(unsigned char)c; }
static void puts(const char *s) { while (*s) { if (*s == '\n') putc('\r'); putc(*s++); } }

static void putdec(unsigned int v) {
    char buf[12]; int i = 0;
    if (v == 0) { putc('0'); return; }
    while (v) { buf[i++] = '0' + (v % 10); v /= 10; }
    while (i) putc(buf[--i]);
}

void trap_handler(void) { for (;;) {} }

int main(void) {
    unsigned int a = 0, b = 1, tmp, i;
    puts("=== FIBONACCI ===\n");
    for (i = 0; i < 24; i++) {
        putdec(i); puts(": "); putdec(a); putc('\n');
        tmp = a + b; a = b; b = tmp;
        GPIO_OUTPUT = (unsigned char)(a & 0xff);
    }
    puts("DONE\n");
    for (;;) {}
}