# H3_Retained_145125 bare core

The DUT is `rv32_core` inside the unchanged direct passthrough wrapper `rv32_bare_core`. All eight RTL files match the frozen release byte for byte. All 43 ports and 648 bits preserve their names, widths and directions.

The core excludes caches, external memory services, RAM services, peripherals, UART, PLL and ILA. RV32IMC, predictor and original parameter settings remain enabled. The physical fixture is a separate implementation region.

The extraction miter passes 2,000,000 CPU edges and 4,000,000 full-port comparisons. A controlled input fault fails at edge 10000; the real rollback rerun restores the exact result. The selected fixture passes 179 input patterns, checks all 176 input bits and 471 captured output bits, and verifies its two-edge serial hold and one-edge snapshot latency.

Selected build: `physical/builds/20261101-015628-ffa262ba`. The direct external CPU clock is 145.125 MHz; the actual setup uncertainty is 0.2 ns (minimum requested 0.150 ns). Status: physical_timing_passed; worst setup slack=0.019 ns. All ten slow/fast setup, hold, recovery, removal and pulse-width rows are retained in the independent audit.

Native routed totals: 4550 LUT, 2850 FF, 4 APM, 0 DRM and 0 PLL. Native core hierarchy: 3923 LUT and 1554 FF. Core LUT allocation including generated overhead is bounded by 4143..4147; 3 global LUT slot(s) remain explicit in the reconciliation. Native hierarchy conventions, actual exported primitive ownership and any native-only packed resources remain separate in the linked audit.

The unchanged source completed a full 6000-iteration local RTL CoreMark run: cycles=1743134699; retired=1649428429; UART, CRC and counters equal the frozen reference. That run uses equivalent external cached memory/peripheral services. Its performance and the bare DUT area have those explicit boundaries; the extraction test is not a standalone cacheless benchmark score.

Evidence: `SELECTED_BUILD.json`, `SOURCE_TO_SELECTED_BINDING.json`, `PHYSICAL_ATTEMPTS.json`, `SOURCE_MANIFEST.json`, `source/parameters.json`, `source/BOUNDARY.json` and `INDEPENDENT_SOURCE_AUDIT.json`. The selection links the exact fixture test, extraction test, native routed area reconciliation and full reference run.
