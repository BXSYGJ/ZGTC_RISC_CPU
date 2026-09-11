#include "platform.h"
#define SAMPLE_COUNT 256u
typedef struct { u32 cycle; u32 pins; } sample_record;
static sample_record samples[SAMPLE_COUNT];
static u32 valid_capture, late_samples, trigger_mask;
static u32 cycles_now(void) {
    u32 value;
    __asm__ volatile ("csrr %0, mcycle" : "=r"(value));
    return value;
}
static void output_char(unsigned char value) {
    uart_putc(value);
#if CONSOLE_DELAY_CYCLES > 0
    u32 started = cycles_now();
    while ((u32)(cycles_now() - started) < CONSOLE_DELAY_CYCLES) { }
#endif
}
static void output_text(const char *text) {
    while (*text) output_char((unsigned char)*text++);
}
static void output_hex(u32 value, unsigned int digits) {
    for (unsigned int digit = digits; digit > 0; digit--) {
        u32 nibble = (value >> ((digit - 1u) * 4u)) & 15u;
        output_char((unsigned char)(nibble < 10u ? '0' + nibble : 'a' + nibble - 10u));
    }
}
static void discard_rx(void) {
    while (UART_STATUS & 4u) { (void)UART_DATA; }
}
static void capture(u32 mask, u32 rising) {
    valid_capture = 0;
    trigger_mask = mask;
    GPIO_OUTPUT = 2;
    uart_puts("ARMED\n");
    u32 previous = GPIO_INPUT & mask;
    u32 armed_at = cycles_now();
    STATUS_CODE = 0xa1100001u;
    for (;;) {
        u32 current = GPIO_INPUT & mask;
        if (rising ? (!previous && current) : (previous && !current)) break;
        previous = current;
        if ((u32)(cycles_now() - armed_at) >= APP_TIMEOUT_CYCLES) {
            output_text("TIMEOUT\n");
            STATUS_CODE = 0xa1100000u;
            GPIO_OUTPUT = 1;
            return;
        }
    }
    STATUS_CODE = 0xa1100002u;
    GPIO_OUTPUT = 4;
    late_samples = 0;
    u32 origin = cycles_now();
    u32 deadline = origin;
    for (u32 index = 0; index < SAMPLE_COUNT; index++) {
        while ((int)(cycles_now() - deadline) < 0) { }
        u32 pins = GPIO_INPUT;
        u32 timestamp = cycles_now();
        samples[index].cycle = timestamp - origin;
        samples[index].pins = pins & 3u;
        if ((u32)(timestamp - deadline) >= APP_SAMPLE_CYCLES) {
            late_samples++;
            deadline = timestamp + APP_SAMPLE_CYCLES;
        } else deadline += APP_SAMPLE_CYCLES;
    }
    valid_capture = 1;
    discard_rx();
    STATUS_CODE = 0xa1100003u;
    GPIO_OUTPUT = 8;
    output_text("DONE\n");
}
static void dump_capture(void) {
    if (!valid_capture) { output_text("EMPTY\n"); return; }
    STATUS_CODE = 0xa1100004u;
    GPIO_OUTPUT = 16;
    output_text("SCOPE1 count=00000100 period=");
    output_hex(APP_SAMPLE_CYCLES, 8);
    output_text(" clock=019bfcc0 trigger=");
    output_hex(trigger_mask, 2);
    output_char('\n');
    u32 checksum = 2166136261u;
    for (u32 index = 0; index < SAMPLE_COUNT; index++) {
        output_hex(samples[index].cycle, 8);
        output_char(':');
        output_hex(samples[index].pins, 2);
        output_char('\n');
        checksum = (checksum ^ samples[index].cycle) * 16777619u;
        checksum = (checksum ^ samples[index].pins) * 16777619u;
    }
    output_text("END checksum=");
    output_hex(checksum, 8);
    output_text(" late=");
    output_hex(late_samples, 8);
    output_char('\n');
    STATUS_CODE = 0xa1100003u;
    GPIO_OUTPUT = 8;
}
void trap_handler(void) {
    GPIO_OUTPUT = 0xee;
    STATUS_CODE = 0xdead00fau;
    output_text("SCOPE TRAP\n");
    for (;;) { }
}
int main(void) {
    UART_CONTROL = 0;
    GPIO_ENABLE = 0;
    STATUS_CODE = 0xa1100000u;
    GPIO_OUTPUT = 1;
    output_text("ZGTC SCOPE READY: A=RX-fall K=KEY-rise D=dump ?=help\n");
    for (;;) {
        u32 command = UART_DATA;
        if (command == 'A') capture(2, 0);
        else if (command == 'K') capture(1, 1);
        else if (command == 'D') dump_capture();
        else if (command == '?') output_text("A RX-fall; K KEY-rise; D dump; 256 samples; timestamps after GPIO read\n");
    }
}
