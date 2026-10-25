#include "boardsupport.h"
#define REG(a) (*(volatile uint32_t *)(a))
#ifndef WORKLOAD_NAME
#error WORKLOAD_NAME must identify the frozen workload
#endif
#ifndef CONSOLE_DELAY_CYCLES
#define CONSOLE_DELAY_CYCLES 2700000u
#endif
static uint64_t begin_cycles, begin_retired, elapsed_cycles, elapsed_retired;
static uint64_t snapshot_read(uint32_t address) {
    uint32_t lo = REG(address), hi = REG(address + 4);
    return ((uint64_t)hi << 32) | lo;
}
static void putc_uart(char c) {
    while (!(REG(0x10000104u) & 1u)) {}
    REG(0x10000100u) = (unsigned char)c;
    uint32_t begin = REG(0x10000300u);
    while ((uint32_t)(REG(0x10000300u) - begin) < CONSOLE_DELAY_CYCLES) {}
}
static void puts_uart(const char *s) { while (*s) putc_uart(*s++); }
static void hex64(uint64_t v) {
    const char *digits = "0123456789abcdef";
    for (int i = 60; i >= 0; i -= 4) putc_uart(digits[(v >> i) & 15]);
}
void initialise_board(void) {
    REG(0x10000108u) = 0;
    REG(0x10000000u) = 0xeb000010u;
    puts_uart("EMBENCH READY " WORKLOAD_NAME " send G\n");
    while (REG(0x10000100u) != 0x47u) {}
    puts_uart("EMBENCH START " WORKLOAD_NAME " heat=1 scale=1 clock_hz=153000000\n");
    while (!(REG(0x10000104u) & 2u)) {}
    REG(0x10000000u) = 0xeb000000u;
}
void start_trigger(void) {
    __asm__ volatile ("" ::: "memory");
    REG(0x10000400u) = 1;
    begin_cycles = snapshot_read(0x10000410u);
    begin_retired = snapshot_read(0x10000418u);
    __asm__ volatile ("" ::: "memory");
}
void stop_trigger(void) {
    __asm__ volatile ("" ::: "memory");
    REG(0x10000400u) = 1;
    elapsed_cycles = snapshot_read(0x10000410u) - begin_cycles;
    elapsed_retired = snapshot_read(0x10000418u) - begin_retired;
    __asm__ volatile ("" ::: "memory");
}
void finish_benchmark(int verified) {
    puts_uart("EMBENCH cycles=0x"); hex64(elapsed_cycles);
    puts_uart(" retired=0x"); hex64(elapsed_retired);
    puts_uart(verified == 1 ? " verified=1\n" : " verified=0\n");
    puts_uart("EMBENCH FINISHED " WORKLOAD_NAME "\n");
    while (!(REG(0x10000104u) & 2u)) {}
    REG(0x10000000u) = verified == 1 ? 0xeb000001u : 0xeb0000ffu;
}
void trap_handler(void) { puts_uart("EMBENCH TRAP " WORKLOAD_NAME "\n"); REG(0x10000000u) = 0xeb0000feu; for (;;) {} }
