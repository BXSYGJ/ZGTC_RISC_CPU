/* Flash bootloader for the ZGTC RV32I SoC.
 *
 * Lives in the first 4 KB of BRAM and is baked into the bitstream once.
 * On reset it looks for a valid application image in the on-board user SPI
 * flash (U9); if one is present it is copied into BRAM at APP_BASE and
 * launched. Otherwise the bootloader drops into a UART recovery console so a
 * new application can be sent over the serial port and written to flash,
 * which means changing the application never requires re-synthesis.
 */
#define MMIO_BASE 0x10000000u
#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))

#define UART_DATA   REG32(0x100u)
#define UART_STATUS REG32(0x104u)
#define GPIO_INPUT  REG32(0x204u)
#define SPI_CTRL    REG32(0x500u)
#define SPI_TX      REG32(0x504u)
#define SPI_RX      REG32(0x508u)

#define TX_READY 0x1u
#define RX_VALID 0x4u
#define KEY_BIT  0x2u          /* gpio_input[1] = ~key, high while pressed */

#define APP_BASE 0x1000u       /* application load/execute address */
#define APP_MAX  0xf000u       /* 60 KB of the 64 KB BRAM */
#define MAGIC    0x50434652u   /* "RFCP" read back little-endian */
#define HEADER   8u            /* magic[4] + length[4] */
#define PAGE     256u
#define SECTOR   0x1000u

#define CMD_READ   0x03u
#define CMD_WREN   0x06u
#define CMD_PP     0x02u
#define CMD_SE     0x20u
#define CMD_RDSR   0x05u
#define CMD_JEDEC  0x9fu

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

/* An SPI_TX write holds its bus response until the byte has been shifted,
   so a transfer is just "write, then read SPI_RX". */
static unsigned char spi_xfer(unsigned char value) {
    SPI_TX = (unsigned int)value;
    return (unsigned char)(SPI_RX & 0xffu);
}

static void flash_select(void) { SPI_CTRL = 1u; }
static void flash_release(void) { SPI_CTRL = 0u; }

/* Poll status register-1 until WIP clears. Returns 0 on success, 1 on
   timeout so a dead/mis-wired flash cannot hang the bootloader forever. */
static int flash_wait_ready(void) {
    unsigned long polls = 0u;
    flash_select();
    spi_xfer(CMD_RDSR);
    while ((spi_xfer(0xffu) & 0x01u) != 0u) {
        if (++polls > 2000000u) {
            flash_release();
            return 1;
        }
    }
    flash_release();
    return 0;
}

/* Read the 3-byte JEDEC ID (command 0x9f) into the buffer. */
static void flash_jedec_id(unsigned char id[3]) {
    flash_select();
    spi_xfer(CMD_JEDEC);
    id[0] = spi_xfer(0xffu);
    id[1] = spi_xfer(0xffu);
    id[2] = spi_xfer(0xffu);
    flash_release();
}

static void flash_wren(void) {
    flash_select();
    spi_xfer(CMD_WREN);
    flash_release();
}

static void flash_read(unsigned int address, unsigned char *destination, unsigned int count) {
    flash_select();
    spi_xfer(CMD_READ);
    spi_xfer((unsigned char)(address >> 16));
    spi_xfer((unsigned char)(address >> 8));
    spi_xfer((unsigned char)address);
    for (unsigned int index = 0u; index < count; index++) {
        destination[index] = spi_xfer(0xffu);
    }
    flash_release();
}

static int flash_program_page(unsigned int address, const unsigned char *source, unsigned int count) {
    flash_wren();
    flash_select();
    spi_xfer(CMD_PP);
    spi_xfer((unsigned char)(address >> 16));
    spi_xfer((unsigned char)(address >> 8));
    spi_xfer((unsigned char)address);
    for (unsigned int index = 0u; index < count; index++) {
        spi_xfer(source[index]);
    }
    flash_release();
    return flash_wait_ready();
}

/* Programs without crossing a 256-byte page boundary. */
static int flash_program(unsigned int address, const unsigned char *source, unsigned int count) {
    unsigned int offset = 0u;
    while (offset < count) {
        unsigned int at = address + offset;
        unsigned int chunk = PAGE - (at & (PAGE - 1u));
        if (chunk > count - offset) chunk = count - offset;
        if (flash_program_page(at, source + offset, chunk) != 0) return 1;
        offset += chunk;
    }
    return 0;
}

static int flash_erase(unsigned int bytes) {
    for (unsigned int address = 0u; address < bytes; address += SECTOR) {
        flash_wren();
        flash_select();
        spi_xfer(CMD_SE);
        spi_xfer((unsigned char)(address >> 16));
        spi_xfer((unsigned char)(address >> 8));
        spi_xfer((unsigned char)address);
        flash_release();
        if (flash_wait_ready() != 0) return 1;
    }
    return 0;
}

/* Launch the application: push the bootloader's writes out to BRAM and
   invalidate the instruction cache before jumping. */
static void launch(void) {
    void (*application)(void) = (void (*)(void))APP_BASE;
    __asm__ volatile("fence.i" ::: "memory");
    application();
}

/* Copy the image from flash into BRAM and launch it. Returns 0 when no
   usable image is present. */
static int boot_from_flash(void) {
    unsigned char header[HEADER];
    unsigned int length;
    flash_read(0u, header, HEADER);
    unsigned int magic = ((unsigned int)header[0]) |
                         (((unsigned int)header[1]) << 8) |
                         (((unsigned int)header[2]) << 16) |
                         (((unsigned int)header[3]) << 24);
    length = ((unsigned int)header[4]) |
             (((unsigned int)header[5]) << 8) |
             (((unsigned int)header[6]) << 16) |
             (((unsigned int)header[7]) << 24);
    if (magic != MAGIC || length == 0u || length > APP_MAX) return 0;
    flash_read(HEADER, (unsigned char *)APP_BASE, length);
    launch();
    return 1;
}

static void store_image_header(unsigned char *header, unsigned int length) {
    header[0] = (unsigned char)(MAGIC & 0xffu);
    header[1] = (unsigned char)((MAGIC >> 8) & 0xffu);
    header[2] = (unsigned char)((MAGIC >> 16) & 0xffu);
    header[3] = (unsigned char)((MAGIC >> 24) & 0xffu);
    header[4] = (unsigned char)(length & 0xffu);
    header[5] = (unsigned char)((length >> 8) & 0xffu);
    header[6] = (unsigned char)((length >> 16) & 0xffu);
    header[7] = (unsigned char)((length >> 24) & 0xffu);
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
        if (command == 'W') {
            unsigned int length = receive_image();
            if (length != 0u && length != RX_ABORT) {
                unsigned char header[HEADER];
                store_image_header(header, length);
                if (flash_erase(HEADER + length + SECTOR - 1u) != 0) {
                    uart_print("ERR erase\n");
                } else if (flash_program(0u, header, HEADER) != 0 ||
                           flash_program(HEADER, (const unsigned char *)APP_BASE, length) != 0) {
                    uart_print("ERR write\n");
                } else {
                    uart_print("FLASHED\r\n");
                    if (boot_from_flash() == 0) uart_print("ERR verify\n");
                }
            }
        } else if (command == 'J') {
            unsigned char id[3];
            flash_jedec_id(id);
            uart_print("JEDEC ");
            uart_putc("0123456789abcdef"[id[0] >> 4]);
            uart_putc("0123456789abcdef"[id[0] & 0x0f]);
            uart_putc(' ');
            uart_putc("0123456789abcdef"[id[1] >> 4]);
            uart_putc("0123456789abcdef"[id[1] & 0x0f]);
            uart_putc(' ');
            uart_putc("0123456789abcdef"[id[2] >> 4]);
            uart_putc("0123456789abcdef"[id[2] & 0x0f]);
            uart_print("\r\n");
        } else if (command == 'R') {
            unsigned int length = receive_image();
            if (length != 0u && length != RX_ABORT) {
                uart_print("RUN\r\n");
                launch();
            }
        } else if (command == 'B') {
            if (boot_from_flash() == 0) uart_print("ERR no image\n");
        } else if (command == 'E') {
            flash_erase(SECTOR);
            uart_print("ERASED\r\n");
        } else if (command == '?') {
            uart_print("W<len32><bin> flash+boot  R<len32><bin> run  B boot  E erase  J jedec\n");
        } else {
            uart_print("?\r\n");
        }
    }
}

void main_boot(void) {
    flash_release();
    if ((GPIO_INPUT & KEY_BIT) == 0u) {
        if (boot_from_flash() != 0) {
            /* Not reached: the application takes over. */
        }
    }
    console();
    for (;;) { }
}
