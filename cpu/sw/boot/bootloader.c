/* UART bootloader for the ZGTC RV32I SoC.
 *
 * Lives in the first 4 KB of BRAM and is baked into the bitstream once.
 * On reset it drops into a UART recovery console so an application image can
 * be sent over the serial port, loaded into BRAM at APP_BASE and launched.
 * There is no SPI flash dependency: the application is RAM-only and does not
 * persist across power cycles.
 */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))

#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)

#define TX_READY 0x1u
#define RX_VALID 0x4u

#define APP_BASE 0x1000u       /* application load/execute address */
#define APP_MAX  0xf000u       /* 60 KB of the 64 KB BRAM */

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
        /* ~20 s of idle at 27 MHz: the remote lab can stall host->board UART
           delivery for several seconds between bursts, so a short timeout
           would abort perfectly good large transfers. */
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

static void console(void) {
    uart_print("ZBOOT\r\n");
    for (;;) {
        uart_print(">");
        unsigned char command = uart_getc();
        if (command == 'R') {
            unsigned int length = receive_image();
            if (length != 0u && length != RX_ABORT) {
                uart_print("RUN\r\n");
                launch();
            }
        } else if (command == '?') {
            uart_print("R<len32><bin> load+run\n");
        } else {
            uart_print("?\r\n");
        }
    }
}

void main_boot(void) {
    console();
    for (;;) { }
}