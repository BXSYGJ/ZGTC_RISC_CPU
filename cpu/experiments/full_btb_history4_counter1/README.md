# Four-bit local history with one-bit counters: negative screen

This variant changes only the qualified predictor defaults to HISTORY_BITS=4 and COUNTER_BITS=1. Sixteen one-bit counter banks hold the same 4096 declared counter bits as the parent's eight two-bit banks, while history state grows by 256 bits. That arithmetic is not a measured LUT/FF saving, and counter hysteresis is intentionally removed rather than claimed equivalent.

Both ten-iteration full-SoC runs preserve CRC and retired counts but worsen execution: V0 takes 3064639 cycles versus 3004340 (60299 more), and V1 takes 3066105 versus 3007840 (58265 more). The independent model passes 96 parameter configurations, 18 compiled negative controls, two observationally equivalent cases and twelve original-reference comparisons across four test methods. Its high-history-bit mutation is rejected.

Evidence is retained in build/v0, build/v1 and build/predictor-regressions.log. This candidate is not selected for PDS because both tested seeds regress and it has no measured compensating resource/timing advantage. This is a bounded screening decision, not a proof of global predictor optimality or a substituted long-run metric. GPIO, UART and all other SoC RTL remain unchanged. No baseline, browser or GitHub state changes.
