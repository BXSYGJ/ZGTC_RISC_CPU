/* ---------------------------------------------------------------------------
 * main.c -- InstRec control-core firmware (RV32IM)
 *
 * What it demonstrates on the board, in order:
 *   1. the core executes from ROM and talks to the system over MMIO,
 *   2. an ISA self-test (RV32I ALU/branch/load-store, RV32M when ENABLE_M),
 *   3. a self-measured cycle/instruction count (mcycle / minstret),
 *   4. live supervision of the InstRec NPU: every finished inference is read
 *      back (top-1 class + percentage) and printed over the shared UART,
 *      plus the DDR3 self-test verdict reported by sys_ctrl.
 *
 * Output tokens used by scripts/board_check.py --expect:
 *   "RV32 BOOT"  "RV32 ISA OK"  "RV32 MMIO OK"  "RV32 BENCH"  "NPU top1="
 * ------------------------------------------------------------------------- */
#include <stdint.h>
#include "ui_transition.h"

#define MMIO(a) (*(volatile uint32_t *)(a))
#define SYS_ID      MMIO(0x80000000u)
#define SYS_STATUS  MMIO(0x80000004u)
#define SYS_PROBS   MMIO(0x80000008u)
#define UART_TX     MMIO(0x8000000cu)
#define UART_ST     MMIO(0x80000010u)
#define LED_REG     MMIO(0x80000014u)
#define CYCLE_LO    MMIO(0x80000018u)
#define INSTRET_LO  MMIO(0x8000001cu)
#define DDR_STS     MMIO(0x80000020u)
#define NPU_CTRL    MMIO(0x80000024u)
#define NPU_CYCLES  MMIO(0x80000028u)

#define RESULT_SEQ  MMIO(0x8000002cu)
#define RESULT_LO   MMIO(0x80000030u)
#define RESULT_HI   MMIO(0x80000034u)
#define RESULT_TOP1 MMIO(0x80000038u)
#define UI_PUBLISH  MMIO(0x80000040u)
#define HIST_PUBLISH MMIO(0x80000044u)
#define UI_TOP1     MMIO(0x80000048u)

#define ST_NPU_BUSY    (1u << 0)
#define ST_NPU_DONE    (1u << 1)
#define ST_NPU_TIMEOUT (1u << 2)
#define ST_PROBS       (1u << 3)
#define ST_DDR_OK      (1u << 5)
#define ST_DDR_ERR     (1u << 6)

static void putc_(char c) {
    while ((UART_ST & 1u) == 0u) { }
    UART_TX = (uint32_t)(unsigned char)c;
}

static void puts_(const char *s) {
    while (*s) putc_(*s++);
}

static void puthex(uint32_t v) {
    int i;
    putc_('0');
    putc_('x');
    for (i = 28; i >= 0; i -= 4) {
        uint32_t d = (v >> (unsigned)i) & 0xfu;
        putc_(d < 10u ? (char)('0' + d) : (char)('a' + (d - 10u)));
    }
}

static void putdec(uint32_t v) {
    char buf[11];
    int n = 0;
    if (v == 0u) { putc_('0'); return; }
    while (v && n < 10) { buf[n++] = (char)('0' + (v % 10u)); v /= 10u; }
    while (n) putc_(buf[--n]);
}

static uint32_t read_mcycle(void) { uint32_t v; __asm__ volatile ("csrr %0, mcycle" : "=r"(v)); return v; }
static uint32_t read_minstret(void) { uint32_t v; __asm__ volatile ("csrr %0, minstret" : "=r"(v)); return v; }

void trap_handler(void) {
    uint32_t cause;
    __asm__ volatile ("csrr %0, mcause" : "=r"(cause));
    puts_("\r\nRV32 TRAP ");
    puthex(cause);
    puts_("\r\n");
    for (;;) { }
}

/* --- ISA self-test: returns 0 on pass, otherwise the failing test id ---- */
static uint32_t isa_test(void) {
    static volatile uint32_t scratch[8];
    volatile uint32_t *ram = scratch;
    volatile uint8_t  *ram8 = (volatile uint8_t *)scratch;
    uint32_t i, sum = 0;
    int32_t s;

    /* 1: arithmetic + branch */
    for (i = 1; i <= 100u; i++) sum += i;
    if (sum != 5050u) return 1u;

    /* 2: word / half / byte store-load with sign extension */
    ram[4] = 0x12345678u;
    if (ram[4] != 0x12345678u) return 2u;
    ram8[20] = 0xa5u;
    if (ram8[20] != 0xa5u) return 3u;
    ram[6] = 0xdeadbeefu;
    if ((uint16_t)ram[6] != 0xbeefu) return 4u;

    /* 3: shift / compare / logic */
    if ((0x80000000u >> 1) != 0x40000000u) return 5u;
    s = (int32_t)0x80000000u;
    if ((s >> 1) != (int32_t)0xc0000000u) return 6u;
    if (!(0xf0f0u ^ 0xffffu) || ((0x0f0fu & 0x3c3cu) != 0x0c0cu)) return 7u;

#ifdef ENABLE_M
    /* 4: RV32M multiply / divide / remainder */
    if (7u * 6u != 42u) return 8u;
    if ((100u / 7u) != 14u || (100u % 7u) != 2u) return 9u;
    if ((int32_t)(-100) / 7 != -14 || (int32_t)(-100) % 7 != -2) return 10u;
    if ((0x12345678u * 0x10u) != 0x23456780u) return 11u;
#endif

    return 0u;
}

int main(void) {
    uint32_t t0, t1, i0, i1, i, acc = 0, status;
    uint32_t sequence = 0, start_cycle = 0, last_step = UI_STEPS;
    uint32_t target_top1 = 0, display_initialized = 0;
    static ui_transition animation;
    uint8_t target[8], display[8], history[8];

    LED_REG = 0x01u;                       /* proof of life for led[0] */
    puts_("\r\nRV32 BOOT\r\n");

    if (SYS_ID != 0x52564331u) {
        puts_("RV32 MMIO FAIL ");
        puthex(SYS_ID);
        puts_("\r\n");
    } else {
        puts_("RV32 MMIO OK\r\n");
    }

    {
        uint32_t rc = isa_test();
        if (rc) {
            puts_("RV32 ISA FAIL ");
            putdec(rc);
            puts_("\r\n");
        } else {
            puts_("RV32 ISA OK\r\n");
        }
    }

    /* mcycle / minstret self-measurement over a fixed integer workload */
    t0 = read_mcycle();
    i0 = read_minstret();
    for (i = 0; i < 20000u; i++) {
        acc += (i ^ (acc >> 3));
        if (acc & 1u) acc ^= 0x5a5a5a5au;
    }
    t1 = read_mcycle();
    i1 = read_minstret();
    puts_("RV32 BENCH cycles=");
    putdec(t1 - t0);
    puts_(" inst=");
    putdec(i1 - i0);
    puts_(" acc=");
    puthex(acc);
    puts_("\r\n");

    status = SYS_STATUS;
    puts_("DDR ");
    puts_((status & ST_DDR_OK) ? "OK" : ((status & ST_DDR_ERR) ? "ERR" : "WAIT"));
    puts_(" STS ");
    puthex(DDR_STS);
    puts_("\r\n");

    /* The control core owns one explicit accelerator launch.  The normal
     * audio-window path may also start inference, but this command proves the
     * CPU-to-NPU MMIO control path independently of the audio producer. */
    NPU_CTRL = 0x1u;
    puts_("NPU GO\r\n");

    for (;;) {
        uint32_t observed = RESULT_SEQ;
        status = SYS_STATUS;
        if (observed != sequence) {
            uint32_t lo, hi, top1;
            /* Retry if a new complete vector arrives during the MMIO reads. */
            do {
                observed = RESULT_SEQ;
                lo = RESULT_LO;
                hi = RESULT_HI;
                top1 = RESULT_TOP1;
            } while (RESULT_SEQ != observed);
            sequence = observed;
            for (i = 0; i < 4; ++i) {
                target[i] = (uint8_t)(lo >> (i * 8u));
                target[i + 4u] = (uint8_t)(hi >> (i * 8u));
            }
            target_top1 = top1;
            ui_proportions(target, history);
            {
                uint32_t boundary = 0;
                for (i = 0; i < 8; ++i) {
                    boundary += history[i];
                    HIST_PUBLISH = (boundary << 8) | i;
                }
            }
            ui_retarget(&animation, target);
            start_cycle = read_mcycle();
            last_step = 0u;
            if (!display_initialized) {
                /* There is no old result to fade out on the first inference. */
                start_cycle -= UI_PHASE_STEPS * UI_TICK_CYCLES;
                last_step = UI_PHASE_STEPS;
                UI_TOP1 = target_top1;
                display_initialized = 1u;
            }
            puts_("NPU top1=");
            putdec(top1);
            puts_(" last_class=7 last_p=");
            putdec(target[7]);
            puts_(" c=");
            putdec(NPU_CYCLES);
            puts_("\r\n");
            NPU_CTRL = 0x2u;
            NPU_CTRL = 0x1u;
            LED_REG = 0x80u | (top1 << 4);
        } else if (status & ST_NPU_TIMEOUT) {
            puts_("NPU TIMEOUT\r\n");
            NPU_CTRL = 0x2u;
        }
        if (last_step < UI_STEPS) {
            uint32_t step = (read_mcycle() - start_cycle) / UI_TICK_CYCLES;
            if (step > UI_STEPS) step = UI_STEPS;
            if (step != last_step) {
                ui_step(&animation, step, display);
                if (step >= UI_PHASE_STEPS) UI_TOP1 = target_top1;
                for (i = 0; i < 8; ++i)
                    UI_PUBLISH = ((uint32_t)display[i] << 8) | i;
                last_step = step;
            }
        }
    }
}
