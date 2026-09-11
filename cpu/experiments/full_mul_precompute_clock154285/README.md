# Compact multiply precompute at 154.286 MHz

Parent: `../full_mul_precompute` (8388B9ED CPU). No duplicated WB comparator. CPU and all peripheral RTL remain byte-identical to that parent; only PLL configuration, clock allowlists, and matching firmware change. GPIO, UART and full 42-data/33-trigger/1024-depth ILA requirements remain mandatory.

The PLL divides a 1080 MHz VCO by seven. Exact modeled output is 154285714 + 2/7 Hz; firmware uses integer 154285714 Hz, a documented sub-hertz representation difference. Native WSL vendor simulation has verified the selected configuration, and final-stage verification must also pass. This is not a measured oscillator frequency or a physical timing result.

The user permits this clock reduction only while absolute CoreMark stays at least 501.0657302224314, execution efficiency at least 3.181369715697977 CoreMark/MHz, and resource efficiency at least 0.053452712846429634 CoreMark/LUT. Short-run expectations do not qualify those gates. Fresh matching V0/V1 firmware, simulations, full-ILA physical results and board tests are required.

## Inputs and current runs

`source-inputs.json` proves that the only physical source change from the precompute parent is the PLL file; CPU/peripheral/constraints are identical. Both edited PowerShell entrypoints retain UTF-8 BOM and pass the PS7 parser. Four firmware images were rebuilt from the locally pinned, clean CoreMark source: V0/V1 with 10 iterations and V0/V1 with 6000 iterations. Old-frequency firmware is not reused.

Ordinary PDS run `build/pds/20260910-192317-0e86d0b4` completed at 154285714 Hz and seed 2: 9024 post-route LUT, 4287 FF and setup WNS -0.027 ns. The timing gate rejected it. This ordinary build does not include the required final ILA and cannot be compared directly to the accepted 9374-LUT full system. Its generated bitstream is not qualified for promotion.

## Matching-clock short tests

New validated builds `20260910-192630-a87a0fa2` (V0) and `20260910-192641-0f23fa4a` (V1) pass with 3060873 and 3065630 cycles respectively, matching the 157.5 MHz precompute parent cycle counts, retired counts and cache statistics. CRCs are fcaf/c64e. These are ten-iteration RTL tests, not formal or hardware CoreMark scores.

The first matching-clock simulation completed its UART transaction but the inherited result parser rejected the new frequency because its allowlist was not yet extended. That rejected run is preserved at `20260910-192246-1539589e`. The isolated parser now admits only the added 154285714 Hz point; four tests verify actual UART parsing and rejection of wrong/unsupported clock, altered CRC/timer/completion, and attempts to score a short run. Both seeds were then rerun in fresh directories; no failed manifest was rewritten to success.

The roughly 153 MHz planning estimate uses the ratio between paired short runs. It is not a direct exact floor against the accepted long-run score; warm-up differences can matter. Promotion must use validated long counters and the exact score/resource comparisons, not that planning estimate.

## Full-function preservation and implementation audit

GPIO and UART functionality may be restructured, but must not be removed or replaced by benchmark-only stubs. ILA must retain the existing 42 data probes, 33 trigger probes, 1024-sample depth and trigger semantics. A lower resource count is not an improvement unless the complete system meets the functional and performance gates.

Full-ILA stage: `build/ila/20260910-mul-precompute-clock154285-seed2`. Actual Inserter verification confirms all 42 data and 33 trigger channels at depth 1024. Pipeline bits 0 and 1 use aliases proven from this build's CPU output connections; no channels were silently discarded. `mapping-audit.json` binds the verified configuration to the actual netlist, ADF, physical source snapshot and matching 6000-iteration V0 firmware. Routing completed with **9493 post-route LUT, 4995 FF and WNS -0.270 ns**. The qualifier rejects timing; on-board capture and long matching-clock qualification remain outstanding. No bitstream was programmed and the accepted baseline remains untouched.

`audit_short.py` re-parses both UART outputs and verifies the executable, firmware and source hashes before comparing the unchanged RTL behavior with the 157.5 MHz precompute parent. Six tests reject altered peripherals/executable, failed simulation, mismatched firmware hash, fabricated rehashed result and modified UART evidence. Seven full-ILA qualification tests check missing/stale outputs, changed inputs and incomplete channel configuration; four clock-parser tests also pass. None of these tests grants hardware or score qualification.

Fresh GPIO integration `build/gpio-tests/20260910-194415-a6e86662` passes both configurations with 2976 checks and three interrupts each. The M-enabled SoC regression passes internal/external UART paths and their fault cases: 74 checks and 23 UART bytes per normal run, 41 checks per fault run. See `build/peripheral-integration-20260910.log`. These simulations do not validate board-level electrical behavior.

The separate comparator child now has validated long RTL counters, but those counters do not qualify this candidate or its different firmware. Even conditionally borrowing its V0 cycle count (1831572143), this 9493-LUT result would yield about 0.05324140 iterations/s/LUT at the configured clock, below the 0.05345271 baseline floor. Therefore this full implementation cannot be promoted based on either timing or that optimistic resource estimate. Do not remove GPIO, UART or ILA channels to change this conclusion.
