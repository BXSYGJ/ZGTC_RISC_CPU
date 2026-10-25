/* Platform harness derived from Embench support/main.c.
 * Copyright (C) 2018-2019 Embecosm Limited.
 * Contributors: James Pallister and Jeremy Bennett.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Workload and library sources remain unchanged. Require explicit verification. */
#include "support.h"
#include "boardsupport.h"
int main(void) {
    volatile int result;
    initialise_board();
    initialise_benchmark();
    warm_caches(WARMUP_HEAT);
    start_trigger();
    result = benchmark();
    stop_trigger();
    finish_benchmark(verify_benchmark(result));
    return 0;
}
