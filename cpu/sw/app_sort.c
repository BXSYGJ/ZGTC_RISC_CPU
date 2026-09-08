/* Bubble sort — sorts a pseudo-random array and prints before/after. */
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
    unsigned int arr[32];
    unsigned int i, j, tmp, seed = 12345;
    puts("=== BUBBLE SORT ===\n");
    /* LCG pseudo-random fill */
    for (i = 0; i < 32; i++) {
        seed = seed * 1103515245u + 12345u;
        arr[i] = seed % 1000;
    }
    puts("BEFORE:\n");
    for (i = 0; i < 32; i++) { putdec(arr[i]); putc(' '); }
    putc('\n');
    /* Bubble sort */
    for (i = 0; i < 31; i++) {
        for (j = 0; j < 31 - i; j++) {
            if (arr[j] > arr[j + 1]) {
                tmp = arr[j]; arr[j] = arr[j + 1]; arr[j + 1] = tmp;
            }
        }
        GPIO_OUTPUT = (unsigned char)(i * 8);
    }
    puts("AFTER:\n");
    for (i = 0; i < 32; i++) { putdec(arr[i]); putc(' '); }
    putc('\n');
    puts("DONE\n");
    for (;;) {}
}