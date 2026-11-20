/* CPU-owned 500 ms fade-in; the outgoing window clears immediately. */
#ifndef UI_TRANSITION_H
#define UI_TRANSITION_H
#include <stdint.h>
#define UI_STEPS 25u
#define UI_TICK_CYCLES 2500000u /* core clock: 125 MHz */
typedef struct {
    int32_t current[8], origin[8], target[8]; /* Q8.8 percentages */
} ui_transition;

static void ui_retarget(ui_transition *s, const uint8_t pct[8]) {
    unsigned i;
    for (i = 0; i < 8; ++i) {
        s->origin[i] = 0;
        s->current[i] = 0;
        s->target[i] = (int32_t)(pct[i] > 100u ? 100u : pct[i]) << 8;
    }
}

static void ui_step(ui_transition *s, unsigned step, uint8_t pct[8]) {
    unsigned i;
    if (step > UI_STEPS) step = UI_STEPS;
    for (i = 0; i < 8; ++i) {
        s->current[i] = s->target[i] * (int32_t)step / (int32_t)UI_STEPS;
        pct[i] = (uint8_t)((s->current[i] + 128) >> 8);
    }
}

/* Cumulative rounding makes every history column sum to exactly 100. */
static void ui_proportions(const uint8_t input[8], uint8_t output[8]) {
    unsigned i, total = 0, cumulative = 0, previous = 0, boundary;
    for (i = 0; i < 8; ++i) total += input[i];
    for (i = 0; i < 8; ++i) {
        cumulative += input[i];
        boundary = total ? (cumulative * 100u + total / 2u) / total : 0u;
        output[i] = (uint8_t)(boundary - previous);
        previous = boundary;
    }
}
#endif
