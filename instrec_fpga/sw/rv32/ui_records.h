#ifndef UI_RECORDS_H
#define UI_RECORDS_H
#include <stdint.h>

/* Session-only ring in the existing CPU data RAM. Raw inference data only. */
typedef struct {
    uint32_t lo, hi, seconds, sequence;
    uint8_t category, bookmark;
} ui_record;
typedef struct {
    ui_record entries[64];
    uint32_t head, count, selected, page, dirty;
} ui_records;

static uint32_t ui_bcd4(uint32_t v) {
    uint32_t b = 0, shift;
    for (shift = 0; shift < 16; shift += 4) {
        b |= (v % 10u) << shift;
        v /= 10u;
    }
    return b;
}
static ui_record *ui_record_at(ui_records *r, uint32_t age) {
    return &r->entries[(r->head - 1u - age) & 63u];
}
static void ui_record_add(ui_records *r, uint32_t lo, uint32_t hi,
                          uint32_t category, uint32_t seconds, uint32_t seq) {
    ui_record *e = &r->entries[r->head];
    e->lo = lo; e->hi = hi; e->category = (uint8_t)category;
    e->seconds = seconds; e->sequence = seq; e->bookmark = 0;
    r->head = (r->head + 1u) & 63u;
    if (r->page && r->count && r->selected < 63u) ++r->selected;
    if (r->count < 64u) ++r->count;
    r->dirty = 1;
}
static void ui_record_keys(ui_records *r, uint32_t events, uint32_t previous) {
    uint32_t changed = events ^ previous;
    if (changed & 0x0000000fu) { r->page ^= 1u; r->selected = 0; }
    if (changed & 0x000f0000u) {
        if (r->count) ui_record_at(r, r->page ? r->selected : 0)->bookmark ^= 1u;
    }
    if (changed & 0x00f000f0u) { r->head = 0; r->count = 0; r->selected = 0; }
    if (r->count) {
        if (changed & 0x0f000f00u) {
            r->page = 1;
            r->selected += (changed & 0x0f000000u) ? 8u : 1u;
            if (r->selected >= r->count) r->selected = r->count - 1u;
        }
        if (changed & 0xf000f000u) {
            uint32_t step = (changed & 0xf0000000u) ? 8u : 1u;
            r->page = 1;
            r->selected = r->selected > step ? r->selected - step : 0;
        }
    }
    if (changed) r->dirty = 1;
}
static void ui_record_row(ui_records *r, uint32_t age, uint32_t *lo, uint32_t *hi) {
    *lo = 0; *hi = 0;
    if (age < r->count) {
        ui_record *e = ui_record_at(r, age);
        uint32_t minute = (e->seconds / 60u) % 100u;
        uint32_t clock = ui_bcd4(minute) << 8 | ui_bcd4(e->seconds % 60u);
        uint32_t pct = (e->category < 4 ? e->lo >> (e->category*8u) :
                         e->hi >> ((e->category-4u)*8u)) & 255u;
        *lo = ui_bcd4(e->sequence) | clock << 16;
        *hi = 0x80000000u | (uint32_t)e->bookmark << 30 |
              (uint32_t)e->category << 26 | ui_bcd4(pct) << 14;
    }
}
#endif
