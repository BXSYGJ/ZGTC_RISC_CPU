/* Mandelbrot set ASCII art — fixed-point, 48x20 grid. */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))
#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)
#define GPIO_OUTPUT REG32(0x200u)
#define TX_READY 0x1u

static void putc(char c) { while ((UART_STATUS & TX_READY) == 0u) {} UART_DATA = (unsigned int)(unsigned char)c; }
static void puts(const char *s) { while (*s) { if (*s == '\n') putc('\r'); putc(*s++); } }

void trap_handler(void) { for (;;) {} }

/* Fixed-point: 16.16 format. Multiply via 64-bit accumulation (no M ext, libgcc handles it). */
#define FONE   65536
#define FSHIFT 16

static int fmul(int a, int b) {
    return (int)(((long long)a * (long long)b) >> FSHIFT);
}

int main(void) {
    int row, col, iter;
    static const char ramp[11] = " .:-=+*#%@";
    puts("=== MANDELBROT ===\n");
    for (row = 0; row < 20; row++) {
        int cy = ((row - 10) * 2 * FONE) / 20;       /* -2.0 .. +2.0 scaled */
        for (col = 0; col < 48; col++) {
            int cx = ((col - 24) * 3 * FONE) / 48;   /* -3.0 .. +3.0 scaled */
            int zx = 0, zy = 0;
            int zx2 = 0, zy2 = 0;
            for (iter = 0; iter < 30; iter++) {
                if (zx2 + zy2 > 4 * FONE) break;
                zy = 2 * fmul(zx, zy) + cy;
                zx = zx2 - zy2 + cx;
                zx2 = fmul(zx, zx);
                zy2 = fmul(zy, zy);
            }
            putc(ramp[iter / 3]);
            GPIO_OUTPUT = (unsigned char)(col);
        }
        putc('\n');
    }
    puts("DONE\n");
    for (;;) {}
}