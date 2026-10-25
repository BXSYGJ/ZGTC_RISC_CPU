/* UART bootloader for the ZGTC RV32IM SoC - PG2L100H (100Pro+) variant.
 *
 * Lives in the first 4 KB of BRAM and is baked into the bitstream once.
 * On reset it drops into a UART recovery console so an application image can
 * be sent over the serial port, loaded into BRAM at APP_BASE and launched.
 * There is no SPI flash dependency: the application is RAM-only and does not
 * persist across power cycles.
 *
 * Derived from cpu/sw/boot/bootloader.c: same ZBOOT console plus the 'D'
 * DDR3 self-test (the 100Pro+ build now has the DDR3 backend:
 * rv32_burst_ddr3 + the Pango DDR3 IP, see pds_cpu_top_100h.v).
 */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))

#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)

#define TX_READY 0x1u
#define RX_VALID 0x4u

#define APP_BASE 0x1000u       /* application load/execute address */
#define APP_MAX  0xf000u       /* 60 KB of the 64 KB BRAM */

#define DDR_BASE 0x00010000u   /* DDR3 starts right above the 64 KB BRAM */
#define DDR_SELFTEST_SIZE 0x10000u   /* 64 KB writable test window */
#define DDR_PATTERN      0x5aa5c3c3u

#define GPIO_INPUT_REG   REG32(0x204u)   /* bit2=pll_lock, bit3=ddr_init_done, bit7=bus timeout */

static void uart_putc(char c) {
    while ((UART_STATUS & TX_READY) == 0u) { }
    UART_DATA = (unsigned int)(unsigned char)c;
}

static void uart_print(const char *text) {
    while (*text != '\0') {
        if (*text == '\n') uart_putc('\r');
        uart_putc(*text++);
    }
}

static unsigned char uart_getc(void) {
    while ((UART_STATUS & RX_VALID) == 0u) { }
    return (unsigned char)(UART_DATA & 0xffu);
}

/* Byte read with an idle timeout so a lost byte cannot hang the bootloader.
   Returns -1 when no byte arrives within the idle budget. */
static int uart_getc_timeout(void) {
    unsigned long idle = 0u;
    while ((UART_STATUS & RX_VALID) == 0u) {
        /* ~20 s of idle at 27 MHz: host->board UART delivery can stall for
           several seconds between bursts, so a short timeout would abort
           perfectly good large transfers. */
        if (++idle > 120000000u) return -1;
    }
    return (int)(UART_DATA & 0xffu);
}

/* Launch the application: push the bootloader's writes out to BRAM and
   invalidate the instruction cache before jumping. */
static void launch(void) {
    void (*application)(void) = (void (*)(void))APP_BASE;
    __asm__ volatile("fence.i" ::: "memory");
    application();
}

/* Tiny nibble hex output used by the DDR report. */
static void uart_put_x(unsigned long value) {
    static const char hex_digits[] = "0123456789abcdef";
    char buffer[9];
    int index, start;
    for (index = 7; index >= 0; index--) {
        buffer[index] = hex_digits[value & 0xfu];
        value >>= 4;
    }
    buffer[8] = '\0';
    start = 0;
    while (start < 7 && buffer[start] == '0') start++;
    uart_print(&buffer[start]);
}

/* DDR3 self test: write a per-word pattern into the DDR window above BRAM,
   force the dirty caches to write back with fence.i, then read it back and
   compare.  Prints DDROK on success or DDRErr @<addr> for the first mismatch.
   The D0/D1... stage markers and the gpio status bits come from the 200H
   bootloader; they isolate a hang to write vs read vs calibration. */
static void ddr_selftest(void) {
    volatile unsigned int *window = (volatile unsigned int *)DDR_BASE;
    unsigned int word, failing, checked;

    /* Phase 1: single-word probe to isolate write vs read hang. */
    {
        unsigned int gpio = GPIO_INPUT_REG;
        uart_print("D0 pll=");
        uart_putc((gpio & 0x4u) ? '1' : '0');
        uart_print(" cpd=");
        uart_putc((gpio & 0x2u) ? '1' : '0');
        uart_print(" init=");
        uart_putc((gpio & 0x8u) ? '1' : '0');
        uart_print(" to=");
        uart_putc((gpio & 0x80u) ? '1' : '0');
        uart_print(" ts=");
        uart_putc('0' + ((gpio >> 4) & 0x7u));
        uart_print("\r\n");
    }
    /* Try a read first - if this hangs, the read path is broken. */
    uart_print("D0r\r\n");
    {
        unsigned int got = window[0];
        unsigned int gpio2 = GPIO_INPUT_REG;
        uart_print("D0rv=");
        uart_put_x(got);
        uart_print(" to=");
        uart_putc((gpio2 & 0x80u) ? '1' : '0');
        uart_print(" ts=");
        uart_putc('0' + ((gpio2 >> 4) & 0x7u));
        uart_print("\r\n");
    }
    uart_print("D1\r\n");
    window[0] = DDR_PATTERN;
    uart_print("D2\r\n");
    __asm__ volatile("fence.i" ::: "memory");
    uart_print("D3\r\n");
    {
        unsigned int got = window[0];
        uart_print("D4\r\n");
        if (got != DDR_PATTERN) {
            uart_print("DDRErr @0x");
            uart_put_x((unsigned long)DDR_BASE);
            uart_print("\r\n");
            return;
        }
    }
    uart_print("D5\r\n");

    for (word = 0u; word < DDR_SELFTEST_SIZE / 4u; word++) {
        window[word] = DDR_PATTERN + word;
    }
    uart_print("D6\r\n");
    __asm__ volatile("fence.i" ::: "memory");
    uart_print("D7\r\n");

    failing = 0xffffffffu;
    checked = 0u;
    for (word = 0u; word < DDR_SELFTEST_SIZE / 4u; word++) {
        if (window[word] != DDR_PATTERN + word) {
            if (failing == 0xffffffffu) failing = word;
        }
        checked++;
        if ((checked & 0xfffu) == 0u) uart_putc('.');
    }
    uart_print("\r\n");
    if (failing == 0xffffffffu) {
        uart_print("DDROK\r\n");
    } else {
        uart_print("DDRErr @0x");
        uart_put_x((unsigned long)(DDR_BASE + failing * 4u));
        uart_print("\r\n");
    }
}

/* Receive a raw application binary over UART into BRAM.
   After every 256 received bytes (and at the end) a 'K' is sent so the host
   can pace the upload against the real drain rate and detect lost bytes.
   A byte-idle timeout aborts instead of hanging. Returns 0xffffffff on abort,
   0 on a bad length, or the image length on success. */
#define RX_ABORT 0xffffffffu
static unsigned int receive_image(void) {
    unsigned int length = 0u;
    int byte;
    for (unsigned int shift = 0u; shift < 32u; shift += 8u) {
        byte = uart_getc_timeout();
        if (byte < 0) { uart_print("ERR rx\n"); return RX_ABORT; }
        length |= ((unsigned int)(unsigned char)byte) << shift;
    }
    if (length == 0u || length > APP_MAX) {
        uart_print("ERR length\n");
        return 0u;
    }
    unsigned char *destination = (unsigned char *)APP_BASE;
    for (unsigned int index = 0u; index < length; index++) {
        byte = uart_getc_timeout();
        if (byte < 0) { uart_print("ERR rx\n"); return RX_ABORT; }
        destination[index] = (unsigned char)byte;
        if ((index & 0xffu) == 0xffu) uart_putc('K');   /* ack each 256-byte block */
    }
    uart_putc('K');                                      /* final ack */
    return length;
}

/* Fatal trap handler: the bootloader has no recovery path, but printing the
   cause and the DDR status bits turns a silent reboot into a diagnosis. */
void trap_handler(void) {
    unsigned int cause, pc, value;
    __asm__ volatile ("csrr %0, mcause" : "=r"(cause));
    __asm__ volatile ("csrr %0, mepc" : "=r"(pc));
    __asm__ volatile ("csrr %0, mtval" : "=r"(value));
    uart_print("\nTRAP cause=");
    uart_put_x((unsigned long)cause);
    uart_print(" pc=");
    uart_put_x((unsigned long)pc);
    uart_print(" tval=");
    uart_put_x((unsigned long)value);
    uart_print("\n");
    {
        unsigned int gpio = GPIO_INPUT_REG;
        uart_print("DDRSTAT pll=");
        uart_putc((gpio & 0x4u) ? '1' : '0');
        uart_print(" cpd=");
        uart_putc((gpio & 0x2u) ? '1' : '0');
        uart_print(" init=");
        uart_putc((gpio & 0x8u) ? '1' : '0');
        uart_print(" to=");
        uart_putc((gpio & 0x80u) ? '1' : '0');
        uart_print(" ts=");
        uart_putc('0' + ((gpio >> 4) & 0x7u));
        uart_print("\n");
    }
    for (;;) { }
}

static void console(void) {
    uart_print("ZBOOT 100H\r\n");
    for (;;) {
        uart_print(">");
        unsigned char command = uart_getc();
        if (command == 'R') {
            unsigned int length = receive_image();
            if (length != 0u && length != RX_ABORT) {
                uart_print("RUN\r\n");
                launch();
            }
        } else if (command == 'D') {
            ddr_selftest();
        } else if (command == 'S') {
            {
                unsigned int gpio = GPIO_INPUT_REG;
                uart_print("S pll=");
                uart_putc((gpio & 0x4u) ? '1' : '0');
                uart_print(" cpd=");
                uart_putc((gpio & 0x2u) ? '1' : '0');
                uart_print(" init=");
                uart_putc((gpio & 0x8u) ? '1' : '0');
                uart_print(" to=");
                uart_putc((gpio & 0x80u) ? '1' : '0');
                uart_print(" ts=");
                uart_putc('0' + ((gpio >> 4) & 0x7u));
                uart_print("\r\n");
            }
        } else if (command == '?') {
            uart_print("R<len32><bin> load+run\n");
            uart_print("D ddr3 selftest\n");
        } else {
            uart_print("?\r\n");
        }
    }
}

void main_boot(void) {
    console();
    for (;;) { }
}
