# Precompute plus late comparator selection

Isolated child of `../full_mul_precompute`; accepted DC90363D hardware baseline is untouched. Preserve UART, GPIO, and 42-data/33-trigger ILA.

The parent full-ILA route has 9373 LUT and fails at -0.251 ns. Its worst path runs from MEM result through branch recovery and ID fire into a late comparator input mux and WB byte-comparison registers. This variant computes ID and held-EX byte relations separately and selects comparison results using ID fire. Kept relation wires discourage recombination into the late input mux. No CPU latency or multiplier behavior is intentionally changed.

## Revised goal

Clock may be moderately reduced, provided CoreMark stays at least 501.0657302224314, execution efficiency stays at least 3.181369715697977 CoreMark/MHz, and resource efficiency stays at least 0.053452712846429634 CoreMark/LUT. The parent short-run ratios suggest a provisional floor near 153 MHz, but paired long measurements and actual timing closure must establish admissibility. No score is inferred from this estimate.

Source-extracted equivalence, actual paired short RTL runs, fresh PDS, full-ILA mapping/routing, long simulations and hardware qualification are required.

## Current verification

Three source-extracted comparator tests pass: exact scoped source delta, 32768 cycles including X/Z controls/data and reset, and four real runtime mutations rejected. The parent and child short V0/V1 results are identical: 3060873/3065630 cycles, matching CRCs, retirement counts, and cache statistics. `audit_short.py` rechecks input/output hashes and normalized compile commands; only CPU RTL differs.

The ordinary 157.5 MHz timing-control build is `build/pds/20260910-185805-fa3b42e6`. Keeping this control frequency measures the effect of the comparator change before selecting a lower clock if needed; it does not reinstate the superseded frequency-nondecreasing requirement.

Initial 6000-iteration RTL runs in `build/compiled/20260910-185913-33137175` (V0) and `build/compiled/20260910-185937-57c1309c` (V1) failed at the imposed cycle limit. The terminal full-ILA result and successful corrected long runs are documented below. Neither an active process nor a provisional short-run estimate is qualification evidence.

## Ordinary-route result

The timing-control run terminated: **9002 post-route LUT, 4277 FF, WNS -0.367 ns** at 157.5 MHz. This fails timing and is not a qualified score. The current worst path has shifted to D-cache request/tag-hit logic, returned load data, `compare_next_wb`, and the WB byte-comparison registers (8 logic levels, 2.127 ns logic and 4.164 ns routing). It is not the parent full-ILA ID-fire input-mux path. No claim of physical improvement follows from comparator equivalence or unchanged short-run cycles.

Any lower-clock candidate needs its own valid PLL/firmware configuration and routed timing; the numerical tradeoff policy alone cannot qualify it. Failed simulation and implementation directories remain preserved.

## Full-ILA terminal result and long-run retry

The child full-ILA run `build/ila/20260910-mul-precompute-compare-seed2` terminated with **9538 post-route LUT, 4996 FF and WNS -0.219 ns** at 157.5 MHz. The 42/33/1024 map is verified, but timing fails. The extra 164 LUT also makes the resource-efficiency floor stricter than the absolute-score floor when reducing frequency. Do not count the short-run speedup as qualified resource efficiency.

The initial two 6000-iteration runs stopped at the imposed 2500000000-cycle limit during slow UART result printing. Both report the explicit cycle-limit failure and lack complete final CRC output. Their partial text is not a validated result. The accepted baseline used MaxCycles=6000000000; new isolated runs use that verified limit: `20260910-191854-9844bd02` (V0) and `20260910-191917-c43b70ee` (V1). The failed directories are preserved.

In parallel, `../full_mul_precompute_clock154285` evaluates the lower-area parent at a moderate lower clock with freshly built matching firmware. This child is not promoted, and no further random seed sweep is underway.

## Completed long RTL counter audit

The corrected V0/V1 runs completed successfully at 19:45:52 and 19:46:12 on September 10, 2026 (Asia/Shanghai). `audit_long.py` verifies source snapshots, current source identity, executable and firmware hashes, complete UART parsing and stored-result identity. Each seed uses the same firmware as its accepted hardware-baseline seed and matches retired instructions, CRCs and the full cache profile.

V0 uses **1831572143 cycles**, V1 **1834527689 cycles**: each saves **54407965 cycles** against its same-seed baseline. V0 execution efficiency calculated from these RTL counters is **3.2758742389324493 iterations/(s * MHz)**. These are RTL results, not hardware measurements or official submitted CoreMark scores. The actual physical build still fails timing.

The exact conditional clock floor for preserving the V0 baseline throughput with these counters is 152956338.88122642 Hz; the V1 same-seed comparison gives 152963448.1755089 Hz. These figures assume unchanged cycles at the new clock and do not include a resource-efficiency guarantee. The child's extra LUT use raises the resource floor. Neither these values nor this child's counters can qualify another RTL/firmware implementation without matching tests. Evidence is `build/long-counter-audit.json`.
