/* Prime sieve — finds all primes below 200 using Sieve of Eratosthenes. */
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
    unsigned char sieve[200];
    unsigned int i, j, count = 0;
    puts("=== PRIMES < 200 ===\n");
    for (i = 0; i < 200; i++) sieve[i] = 1;
    sieve[0] = 0; sieve[1] = 0;
    for (i = 2; i < 200; i++) {
        if (sieve[i]) {
            for (j = i * i; j < 200; j += i) sieve[j] = 0;
        }
    }
    for (i = 2; i < 200; i++) {
        if (sieve[i]) {
            putdec(i); putc(' ');
            count++;
            GPIO_OUTPUT = (unsigned char)(count & 0xff);
        }
    }
    putc('\n');
    puts("Total: "); putdec(count); puts(" primes\n");
    puts("DONE\n");
    for (;;) {}
}