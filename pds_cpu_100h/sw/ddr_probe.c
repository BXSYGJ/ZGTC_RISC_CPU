/* DDR3 data-path diagnostic for the PG2L100H bring-up.
 * Loaded via ZBOOT 'R' at 0x1000 (no bitstream rebuild needed).
 * For each address: cached write, cached read-back, then fence.i and a DDR
 * read-back, so a CPU/cache-side failure is distinguishable from a DDR-side
 * one.  Waits for one UART byte before starting so the host can capture all
 * output. */
#include "platform.h"

static void puthex(u32 v) {
    const char *h = "0123456789abcdef";
    for (int i = 7; i >= 0; i--) uart_putc((unsigned char)h[(v >> (i * 4)) & 0xf]);
}
static void line(const char *tag, u32 addr, u32 wrote, u32 cached, u32 ddrv) {
    uart_puts(tag);
    uart_puts(" a="); puthex(addr);
    uart_puts(" w="); puthex(wrote);
    uart_puts(" c="); puthex(cached);
    uart_puts(" d="); puthex(ddrv);
    uart_puts((cached == wrote && ddrv == wrote) ? " OK\n" : " BAD\n");
}

void trap_handler(void) {
    u32 cause;
    __asm__ volatile ("csrr %0, mcause" : "=r"(cause));
    uart_puts("TRAP cause="); puthex(cause); uart_puts("\n");
    for (;;) { }
}

int main(void) {
    uart_puts("DDRPROBE - send any byte to start\n");
    while ((UART_STATUS & 4u) == 0u) { }
    (void)UART_DATA;
    uart_puts("go\n");

    static const u32 addrs[] = {
        0x00010000u, 0x00010004u, 0x00010010u, 0x00010014u,
        0x00010020u, 0x00010100u, 0x00011000u, 0x00020000u
    };
    for (unsigned i = 0; i < sizeof(addrs) / sizeof(addrs[0]); i++) {
        volatile u32 *p = (volatile u32 *)addrs[i];
        u32 value = 0x12345678u + i;
        *p = value;
        u32 cached = *p;
        __asm__ volatile ("fence.i" ::: "memory");
        u32 ddrv = *p;
        line("T", addrs[i], value, cached, ddrv);
    }
    /* bit-walk on one address: catches stuck/misrouted data bits */
    uart_puts("walk\n");
    volatile u32 *q = (volatile u32 *)0x00010000u;
    for (int bit = 0; bit < 32; bit += 4) {
        u32 value = 0xFu << bit;
        *q = value;
        __asm__ volatile ("fence.i" ::: "memory");
        u32 got = *q;
        line("B", (u32)bit, value, got, got);
    }
    /* large sweep: 4 MB write then verify, with cycle-counted throughput */
    uart_puts("sweep4M\n");
    {
        unsigned start_lo, start_hi, end_lo, end_hi;
        __asm__ volatile ("csrr %0, mcycle" : "=r"(start_lo));
        __asm__ volatile ("csrr %0, mcycleh" : "=r"(start_hi));
        volatile u32 *base = (volatile u32 *)0x00010000u;
        u32 words = (4u << 20) / 4u;
        for (u32 i = 0; i < words; i++) base[i] = 0x5A5A0000u ^ i;
        __asm__ volatile ("fence.i" ::: "memory");
        u32 bad = 0, first = 0;
        for (u32 i = 0; i < words; i++) {
            u32 got = base[i];
            if (got != (0x5A5A0000u ^ i)) { if (!bad) first = i; bad++; }
        }
        __asm__ volatile ("csrr %0, mcycle" : "=r"(end_lo));
        __asm__ volatile ("csrr %0, mcycleh" : "=r"(end_hi));
        u32 cycles = end_lo - start_lo;      /* 32-bit diff is enough (<4G) */
        uart_puts("sweep words="); puthex(words);
        uart_puts(" bad="); puthex(bad);
        if (bad) { uart_puts(" first="); puthex(first); }
        uart_puts(" cycles="); puthex(cycles);
        uart_puts(" MBps=");
        puthex(cycles ? (u32)((8u * 27000000u) / cycles) : 0);  /* 8 MB moved / sec */
        uart_puts("\n");
    }
    uart_puts("DDRPROBE DONE\n");
    for (;;) { }
}
