# RV32IM Soft Processor Complete Evolution History

This document records the complete measured development path of the ZGTC RISC-V CPU project from its initial baseline through the final 153 MHz release. It chronicles every qualified milestone, using timestamps and parent descriptions from experiment documents to distinguish direct parent-child revisions from parallel experiments.

The clock values are configured operating frequencies verified through post-route timing analysis. They are not independent measurements of the FPGA oscillator or claims of absolute physical Fmax.

## Acceptance methodology

Every promoted version was evaluated with its own source snapshot, PLL configuration, constraints, firmware, post-route resource report, timing report, and benchmark evidence. A child implementation was not allowed to inherit the parent's score when its physical implementation, LUT denominator, firmware, or clock configuration changed.

The principal validation gates were:

- RV32IM ISA compliance, cache correctness, peripheral functionality, and pipeline regression testing.
- Fixed CoreMark source code and compiler configuration across all measurements.
- Separate performance (seed 0) and validation (seed 1) firmware images.
- At least 6000 CoreMark iterations and at least ten modeled seconds for complete scoring runs.
- CRC validation, retired-instruction counts, cycle counts, and cache-profile verification.
- Post-route setup timing closure and complete-system resource accounting.
- GPIO, UART retention, and (for later release candidates) 42-data/33-trigger/1024-sample ILA preservation.

Short experiments and timing-failed implementations remain in the chronology for transparency, but they do not receive formal scores unless their timing analysis and long-run evidence both passed.

## Project inception and baseline establishment

### Phase 0 — Initial RV32I baseline without caches

**Parent:** Original course project requirements.

**Document:** [`UNCACHED_BASELINE.md`](UNCACHED_BASELINE.md)

The project began as a basic RV32I implementation without caches, branch prediction, or performance optimization. This initial version established:

- 5-stage in-order pipeline: Fetch → ID → EX → MEM → WB
- Basic hazard detection and pipeline stalls
- M-mode CSR support and precise exception handling
- Direct memory interface without caching
- GPIO, UART, and timer peripherals

The uncached baseline served as the functional foundation but had no performance qualification. All performance measurements begin after cache integration.

### Phase 1 — First board qualification at 27 MHz

**Parent:** Uncached RV32I baseline.

**Documents:** [`HARDWARE_SELFTEST.md`](HARDWARE_SELFTEST.md), [`COREMARK_RESULTS.md`](COREMARK_RESULTS.md)

**Board qualification date:** September 6, 2026

This was the first implementation successfully programmed and tested on physical hardware (PG2L200H FPGA via RemoteLab platform):

- Clock: `27 MHz`
- CoreMark: `9.8178`
- Execution efficiency: `0.3636 CoreMark/MHz`
- Resource usage: `3,735 LUT / 16.5 DRM36K blocks`
- Setup WNS: `+22.869 ns` (at 27 MHz constraint)

The implementation included:

- 2-way set-associative instruction cache (512 bytes)
- 2-way set-associative data cache (512 bytes)
- Write-back, write-allocate D-cache policy
- 4-word cache lines
- Basic branch target buffer (16 entries)
- 64 KiB on-board SRAM
- UART with FIFO buffering
- GPIO and 64-bit timer

This milestone established:

1. **Hardware bring-up methodology**: UART packet validation, GPIO pin verification, interrupt handling.
2. **CoreMark infrastructure**: Two-seed validation (performance + validation), CRC checking, timing instrumentation using 64-bit cycle counters.
3. **Baseline performance floor**: 0.364 CoreMark/MHz, well below the target 3.0 CoreMark/MHz threshold.

The 27 MHz frequency was chosen conservatively for initial board validation. The large timing margin (+22.869 ns) indicated substantial headroom for frequency scaling, but execution efficiency was the immediate priority.

### Phase 2 — M-extension integration at 120 MHz

**Parent:** 27 MHz cached baseline.

**Document:** [`M_EXTENSION.md`](M_EXTENSION.md)

The RV32M extension (integer multiplication and division) was integrated and validated:

- Clock: `120 MHz`
- CoreMark: `149.881`
- Execution efficiency: `1.249 CoreMark/MHz`
- Resource usage: Not explicitly recorded in original documentation

Key architectural changes:

- 32×32→64-bit multiplier using DSP blocks (APM)
- Sequential 32-bit division with early termination
- Multi-cycle M-extension execution in EX stage
- Pipeline stall logic for long-latency operations

This version demonstrated:

1. **Frequency scaling capability**: Successfully operated at 120 MHz, validating PLL configuration and timing methodology.
2. **ISA completeness**: Full RV32IM compliance, passing external test suites (164 RV32UI tests, 32 RV32UM tests).
3. **Performance gap identification**: 1.249 CoreMark/MHz fell far short of the 3.0 target, exposing fundamental execution inefficiencies.

The performance analysis identified critical bottlenecks:

- No data forwarding between pipeline stages
- Conservative cache miss handling
- Suboptimal branch prediction
- Lack of early memory request initiation
- No load-use hazard mitigation beyond full stalls

This measurement established the M-extension as the mandatory baseline ISA and set the clear goal: achieve 3.0 CoreMark/MHz while maintaining or improving frequency.

## Phase 3 — Execution efficiency breakthrough: 3.0 CoreMark/MHz threshold

### R0 — First 120 MHz board milestone with execution optimization

**Parent:** M-extension 120 MHz baseline (1.249 CoreMark/MHz).

**Document:** [`HARDWARE_120MHZ_TARGET.md`](HARDWARE_120MHZ_TARGET.md)

**Board qualification date:** September 6, 2026

This was the first board-qualified version to meet the hard execution efficiency threshold:

- Clock: `120 MHz`
- CoreMark: `361.555751`
- Execution efficiency: `3.0129645923 CoreMark/MHz`
- Resource efficiency: `0.03515369481 CoreMark/LUT`
- Area: `10285 LUT / 4808 FF`
- Setup WNS: `+0.117 ns`

Two performance runs and one post-validation performance run passed on physical hardware (experiment box, device configuration verified).

The implementation combined the mature RV32IM pipeline with aggressive execution optimizations:

**Cache architecture:**
- 8 KiB instruction cache, 2 KiB data cache
- 2-way set-associative organization
- 4-word cache lines
- Write-back, write-allocate D-cache

**Branch prediction:**
- 256-entry direct-mapped BTB
- 2-bit saturating counters
- MEM-stage predictor updates

**Pipeline efficiency:**
- MEM→EX and WB→EX data forwarding
- Early data cache request initiation from EX stage
- Overlapped instruction fetch with prior completion
- Stall preservation of forwarded values

**Compiler optimization:**
- GCC `-O3` optimization level
- Loop unrolling enabled
- Linker relaxation for shorter instruction sequences

**Performance improvement analysis:**

Compared to M-extension baseline:
- Execution efficiency: `1.249` → `3.013 CoreMark/MHz` (+141.3% improvement)
- Absolute throughput: `149.881` → `361.556 CoreMark` (+141.2% improvement)
- Resource cost: `10285 LUT` (first complete accounting)

The main achievement was crossing the `3.0 CoreMark/MHz` execution efficiency threshold on physical hardware. This milestone validated:

1. **Forwarding effectiveness**: Eliminating most pipeline stalls from data dependencies.
2. **Cache impact**: Large I-cache dramatically reduced instruction fetch bottlenecks.
3. **Prediction value**: 256-entry BTB significantly reduced control-flow penalties.

This release was later followed by a smaller-area forward-data qualification record, representing a resource optimization of the same execution efficiency.

### R1 — 120 MHz forward-data qualification

**Parent:** R0 (120 MHz board milestone).

**Document:** [`FORWARD_DATA_QUALIFICATION.md`](FORWARD_DATA_QUALIFICATION.md)

This revision refined the forwarding and data qualification logic while retaining the 120 MHz clock and benchmark behavior. Its purpose was to improve the resource denominator and establish a stronger baseline for subsequent frequency promotion.

The comparison recorded in [`HARDWARE_126MHZ.md`](HARDWARE_126MHZ.md) uses this forward-data version as the 120 MHz reference:

- Execution efficiency: `3.0129645923 CoreMark/MHz` (unchanged)
- Resource efficiency: `0.03555470067 CoreMark/LUT` (+1.14% improvement)
- Area: `10169 LUT` (−116 LUT from R0)
- Setup WNS: `+0.191 ns` (+74 ps improvement)

The execution efficiency remained effectively unchanged; the improvement was concentrated in resource reduction and timing margin. This version demonstrated that the forwarding logic could be restructured without sacrificing execution performance.

## Phase 4 — Frequency scaling and resource optimization (120–144 MHz)

### R2 — 126 MHz cache-lookup version

**Parent:** R1 (120 MHz forward-data qualification).

**Documents:** [`HARDWARE_126MHZ.md`](HARDWARE_126MHZ.md), [`CACHE_LOOKUP_DATA.md`](CACHE_LOOKUP_DATA.md)

This was the first direct frequency promotion after the 120 MHz execution efficiency milestone. Cache lookup timing and PLL configuration were adjusted while preserving processor microarchitecture and CoreMark behavior.

- Clock: `126 MHz`
- CoreMark: `379.634157`
- Execution efficiency: `3.0129694974 CoreMark/MHz`
- Resource efficiency: `0.03718986645 CoreMark/LUT`
- Area: `10208 LUT / 4807 FF`
- Setup WNS: `+0.128 ns`

Compared with R1:
- Frequency: `+5.0%`
- Throughput: `+5.00017%`
- Resource efficiency: `+4.59901%`
- CoreMark/MHz: effectively unchanged

This was a frequency and resource-efficiency improvement, not a meaningful execution-cycle reduction. The small execution efficiency change (3.012964 → 3.012969) was within measurement noise.

### R3 — 132 MHz cache-fanout version

**Parent:** R2 (126 MHz cache-lookup version).

**Documents:** [`HARDWARE_132MHZ.md`](HARDWARE_132MHZ.md), [`CACHE_ADDRESS_FANOUT.md`](CACHE_ADDRESS_FANOUT.md)

This version used cache-address fanout control together with earlier multiplier operand pre-sampling and PLL-source revisions to achieve higher frequency.

- Clock: `132 MHz`
- CoreMark: `397.711974`
- Execution efficiency: `3.0129694974 CoreMark/MHz`
- Resource efficiency: `0.03863531899 CoreMark/LUT`
- Area: `10294 LUT / 5041 FF / 4 APM`
- Setup WNS: `+0.001 ns`

Compared with R2:
- Frequency and throughput: `+4.7619%`
- Resource efficiency: `+3.8867%`
- LUT: `+86`
- FF: `+234`
- CoreMark/MHz: unchanged

The implementation passed three board runs. Its timing margin was narrow (+1 ps), so it was treated as a qualified frequency point rather than proof of maximum frequency capability.

### R4 — 132 MHz folded-BTB and segmented-ALU version

**Parent:** R3 (132 MHz cache-fanout version).

**Documents:** [`HARDWARE_132MHZ_CARRY_SELECT.md`](HARDWARE_132MHZ_CARRY_SELECT.md), [`ALU_CARRY_SELECT.md`](ALU_CARRY_SELECT.md), [`BTB_FOLDED_INDEX.md`](BTB_FOLDED_INDEX.md)

This was the first clear execution-efficiency optimization after crossing the 3.0 CoreMark/MHz threshold:

**Optimizations:**
- Folded BTB indexing logic (XOR-based address compression)
- Segmented ALU arithmetic with parallel carry groups
- Improved multiplier operand timing
- Benchmark firmware and 132 MHz clock unchanged

Results:
- CoreMark: `397.711974` → `399.923110`
- CoreMark/MHz: `3.0129694974` → `3.0297205298` (+0.55596% execution efficiency)
- Resource efficiency: `0.03863531899` → `0.03862871727 CoreMark/LUT` (−0.017% resource efficiency)
- Area: `10353 LUT / 5023 FF`
- Setup WNS: `+0.103 ns` (+102 ps improvement)

The cycle count decreased by approximately 0.553%, while retired instructions and CRC remained unchanged. This was a genuine execution-efficiency gain at constant frequency, demonstrating that microarchitectural refinement could improve performance beyond pure frequency scaling.

Several subsequent address-carry and ALU-preservation experiments were children of this version. They passed functional tests but failed complete timing closure and were not promoted.

### R5 — 141.75 MHz branch-forwarding/LRU version

**Parent:** The 135 MHz branch-forwarding candidate derived from the R4 optimization family; it is a parallel frequency-promotion branch rather than a direct replacement of the R4 board image.

**Document:** [`CLOCK141750.md`](CLOCK141750.md)

This branch combined branch-specific load forwarding with direct-array LRU compression and changed only the PLL for frequency promotion.

- Clock: `141.75 MHz`
- Area: `8662 LUT / 5138 FF`
- Setup WNS: `+0.033 ns`
- CoreMark: `435.578828`
- CoreMark/MHz: `3.072866512`
- CoreMark/LUT: `0.050286173`

Relative to its 135 MHz parent:
- Frequency: `+5%`
- Throughput: `+2.9747%`
- Execution efficiency: `−1.93%`
- Resource efficiency: `+9.61%`

This was a local RTL/PDS qualification, not a new remote-board release. It demonstrated the trade-offs between frequency and execution efficiency, showing that aggressive frequency scaling could sometimes reduce cycles-per-CoreMark efficiency.

### R6 — 144 MHz equal-branch-forwarding version

**Parent:** R5 (141.75 MHz branch-forwarding/LRU version).

**Document:** [`CLOCK144.md`](CLOCK144.md)

This was a direct child of the 141.75 MHz candidate. The processor and forwarding structure were retained while the PLL and clock-specific firmware were regenerated for 144 MHz.

- Clock: `144 MHz`
- Area: `8634 LUT / 5134 FF`
- Setup WNS: `+0.210 ns`
- CoreMark: `442.492778`
- CoreMark/MHz: `3.072866512`
- CoreMark/LUT: `0.051250032`

Compared with R5:
- Frequency and throughput: `+1.5873%`
- Execution efficiency: unchanged
- Resource efficiency: `+1.9167%`
- Execution cycles: unchanged

This is the representative 144 MHz release. Its gain came from frequency and area optimization, not from a new CoreMark cycle reduction. The version established a new resource efficiency benchmark.

## Phase 5 — High-frequency exploration and timing challenges (145–151 MHz)

### R7 — 145.125 MHz load-route-predecode attempt

**Parent:** R6 (144 MHz branch-forwarding version).

**Documents:** [`CLOCK145125.md`](CLOCK145125.md), [`LOAD_ROUTE_PREDECODE.md`](LOAD_ROUTE_PREDECODE.md)

This child attempted to move load-route decoding earlier in the cache/address path to enable higher frequency.

- Clock target: `145.125 MHz`
- Area: `8749 LUT / 5147 FF`
- Setup WNS: `−0.319 ns`
- Result: **timing failure**

It was not assigned a CoreMark score and did not replace R6. This marked the beginning of a series of timing-constrained attempts at frequencies above 144 MHz.

### R8 — 145.125 MHz flattened-cache-data attempt

**Parent:** R7/R6 cache-data-selection branch.

**Documents:** [`CLOCK145125_CACHE_DATA_SELECT.md`](CLOCK145125_CACHE_DATA_SELECT.md), [`CACHE_DATA_SELECT.md`](CACHE_DATA_SELECT.md)

This version flattened cache data selection to shorten the failed 145.125 MHz critical path.

- Area: `8669 LUT / 5139 FF`
- Setup WNS: `−0.171 ns`
- Result: **timing failure**

It reduced area and improved the violation relative to R7 (+148 ps), but still failed timing and therefore had no qualified performance score.

### R9 — 146.25 MHz cache-valid branches

**Parent:** R6/R8 cache-selection family.

**Documents:** [`CLOCK146250_VALID_ENABLE.md`](CLOCK146250_VALID_ENABLE.md), [`CACHE_VALID_ENABLE.md`](CACHE_VALID_ENABLE.md), [`CACHE_VALID_BOTH.md`](CACHE_VALID_BOTH.md), [`CACHE_VALID_REUSE.md`](CACHE_VALID_REUSE.md)

This branch tested multiple cache valid-bit optimizations:
- Sampling valid bits on cache-ready signal
- Reusing valid-bit selection results
- Sampling both cache ways simultaneously
- Retiming cache error classification

The variants were functionally verified, but the complete implementations failed timing. Representative results:

- One cache-valid variant: WNS `−0.231 ns`
- Another variant: WNS `−1.212 ns`

No valid CoreMark score was assigned to these children. These experiments demonstrated that some seemingly logical optimizations could severely degrade timing when implemented in the complete system.

### R10 — 146.25 MHz registered fetch-address selection

**Parent:** R6's 144 MHz fetch-address-selection candidate.

**Documents:** [`FETCH_ADDRESS_SELECT.md`](FETCH_ADDRESS_SELECT.md), [`CLOCK146250_FETCH_ADDRESS_SELECT.md`](CLOCK146250_FETCH_ADDRESS_SELECT.md)

This branch registered or reorganized the fetch-address selection between `fetch_address` and `next_pc`.

- 144 MHz parent: `8793 LUT / 5125 FF / +0.195 ns` WNS
- 146.25 MHz child: Changed only PLL configuration
- Functional traces and execution cycles: unchanged

Results:
- Clock: `146.25 MHz`
- Area: `8843 LUT / 5129 FF`
- Setup WNS: `+0.070 ns`
- CoreMark: `457.481525`
- CoreMark/MHz: `3.128078805`
- CoreMark/LUT: `0.051733747`

Compared with 144 MHz parent:
- Frequency and throughput: `+1.5625%`
- Execution efficiency: unchanged
- Resource efficiency: `−0.92976%`

This was a timing-promotion branch that did not introduce new execution-efficiency improvements. It was a local RTL/PDS qualification, not a remote-board measurement.

### R11 — 148.5 MHz 16-bit address-carry version

**Parent:** The 146.25 MHz load-address-carry branch.

**Documents:** [`LOAD_ADDRESS_CARRY16.md`](LOAD_ADDRESS_CARRY16.md), [`CLOCK148500_CARRY16.md`](CLOCK148500_CARRY16.md)

This branch used parallel 16-bit address-carry groups to reduce the effective address-generation carry path.

- Clock: `148.5 MHz`
- Area: `8677 LUT / 5117 FF`
- Setup WNS: `+0.066 ns`
- CoreMark: `464.519703`
- CoreMark/MHz: `3.128078805`
- CoreMark/LUT: `0.053534598`

Compared with its 146.25 MHz parent:
- Frequency and throughput: `+1.53846%`
- Execution efficiency: unchanged
- Resource efficiency: `+1.67889%`
- Area: `−12 LUT / −7 FF`

This was a locally qualified complete pair, but still not a remote-board baseline. It demonstrated that carry-chain optimization could enable frequency scaling without resource penalty.

### R12 — 151.2 MHz word-load-address branch

**Parent:** R11's load-address branch.

**Documents:** [`WORD_LOAD_ADDRESS.md`](WORD_LOAD_ADDRESS.md), [`WORD_LOAD_ADDRESS_151200.md`](WORD_LOAD_ADDRESS_151200.md)

This branch attempted to shorten word-load address generation and then promoted the clock to 151.2 MHz. The first implementation failed timing:

- Area: `8841 LUT / 5178 FF`
- Setup WNS: `−0.052 ns`
- Result: **timing failure**

The failure exposed a critical path through the timer/exception and fetch-control logic. It was not scored. Later 151.2 MHz children changed the timer, frontend, and ILA physical paths and could not inherit this failed result.

### R13 — 151.2 MHz timer and complete-ILA branches

**Parent:** R12's timing diagnosis.

**Documents:** [`TIMER_COMPARE_SPLIT.md`](TIMER_COMPARE_SPLIT.md), [`OPTIMIZATION_LOG_20260910.md`](OPTIMIZATION_LOG_20260910.md), [`ACCEPTANCE.md`](ACCEPTANCE.md)

This family included multiple optimization attempts:

- Timer compare restructuring
- Timer carry-prefix reduction
- Peripheral read-bank experiments
- Relation reuse
- ILA register-driver remapping
- Cache and frontend control retiming

Several children reduced ordinary CPU area but failed after full ILA insertion. For example:

- One timer-prefix implementation: `151.2 MHz / 9546 LUT / 5076 FF / +0.106 ns` WNS (passed complete ILA timing)
- Did not produce new paired long-run score

Other children reached `9653 LUT` or `9579 LUT` with timing or integration problems and were rejected.

These branches established the methodology for optimizing the complete system (CPU + GPIO + UART + full 42-data/33-trigger/1024-sample ILA) rather than just the CPU-only image. This marked a shift in optimization strategy toward production-ready implementations.

### R14 — 151.2 MHz redirect-priming version

**Parent:** The timing-qualified `full_control_commit` family, after frontend and ILA closure.

**Documents:** [`full_redirect_clock151200/README.md`](../experiments/full_redirect_clock151200/README.md), [`ACCEPTANCE.md`](ACCEPTANCE.md)

Redirect priming used an available fetch opportunity to capture a resolved branch or jump target earlier. It reduced redirect recovery overhead without changing the ISA or retired instruction stream.

Paired short runs showed:
- `3,060,873` → `3,004,340` cycles: `+1.8817%` improvement
- Second pair: approximately `+1.9213%` improvement
- Retired instructions and CRC remained unchanged

Complete local result:
- Clock: `151.2 MHz`
- CoreMark: `504.661492`
- CoreMark/MHz: `3.337708281`
- CoreMark/LUT: `0.0538592841`
- Area: `9370 LUT / 4986 FF`
- Setup WNS: `+0.017 ns`

Relative to DC90363D (the accepted 157.5 MHz board baseline):
- Local execution efficiency: `+4.9142%`
- Throughput: `+0.7176%` (at lower frequency)
- Resource efficiency: `+0.7606%`

This was a local PDS result, not a replacement board measurement. However, it represented a significant execution-efficiency improvement through microarchitectural innovation (redirect priming) rather than pure frequency scaling.

## Phase 6 — High-frequency timing closure and complete-system optimization (154–157.5 MHz)

### R15 — 151.875 MHz timer-compare-split child

**Parent:** The accepted 151.2 MHz timer-compare baseline.

**Document:** [`TIMER_COMPARE_SPLIT_151875.md`](TIMER_COMPARE_SPLIT_151875.md)

The 64-bit timer comparison was split into parallel high- and low-word comparisons without intentionally adding interrupt latency.

- Clock target: `151.875 MHz`
- Area: `8981 LUT / 5185 FF`
- Setup WNS: `−0.068 ns`
- Result: **timing failure**

The child was rejected before full score qualification. This demonstrated that even small frequency steps could fail when critical paths were already near their limits.

### R16 — 154.285714 MHz full commit-enable factoring

**Parent:** The complete-system `full_control_commit` implementation.

**Document:** [`ACCEPTANCE.md`](ACCEPTANCE.md)

This local complete-ILA version factored mutually exclusive write-enable conditions for branches, CSR operations, `MRET`, `FENCE.I`, and ordinary register-writing instructions.

- Clock: `154.285714 MHz`
- CoreMark projection: `505.420596`
- CoreMark/MHz: `3.275874239`
- CoreMark/LUT: `0.0537338503`
- Complete area: `9406 LUT`
- Setup WNS: approximately `0.000 ns`

The change was primarily a control and timing optimization. It did not by itself establish a new board score or prove a CoreMark cycle reduction. The near-zero timing margin indicated this was approaching the frequency limit for this architecture.

### R17 — 157.5 MHz WB-byte-retimed local candidate

**Parent:** The predictor-index and complete-system 157.5 MHz timing branch.

**Documents:** [`WB_BYTE_RETIME.md`](WB_BYTE_RETIME.md), [`COREMARK_500_PLAN.md`](COREMARK_500_PLAN.md)

This version precomputed and registered byte-level equality and ordering information used by EX/WB comparison and branch-control logic.

- Clock: `157.5 MHz`
- Area: `9455 LUT / 5247 FF`
- Setup WNS: `+0.026 ns`
- CoreMark: `501.065730`
- CoreMark/MHz: `3.181369716`
- CoreMark/LUT (this exact image): `0.0529947890`

The optimization closed the high-frequency timing path, but it did not reduce the CoreMark cycle count. The local score was computed from the candidate's own 6000-iteration pair and exact LUT denominator.

This version represented the highest successfully qualified frequency in the project's development timeline before the final release.

### R18 — DC90363D accepted board baseline (157.5 MHz)

**Parent:** R17's WB-retimed complete-system family, with the accepted board image and final complete-system accounting.

**Documents:** [`PROJECT_HANDOVER_153MHZ.md`](PROJECT_HANDOVER_153MHZ.md), [`AI_HANDOFF_153MHZ.md`](AI_HANDOFF_153MHZ.md)

The accepted board baseline was the complete GPIO/UART/cache/ILA image used as the reference for later work:

- Clock: `157.5 MHz`
- CoreMark: `501.065730222`
- CoreMark/MHz: `3.181369716`
- CoreMark/LUT: `0.05345271285`
- Complete-system area: `9374 LUT`
- FF: approximately `4984`
- Setup WNS: approximately `+0.078 ns`

**Board qualification:** September 11, 2026 (experiment box 1, device ID 12)

This was a verified hardware measurement, not a simulation projection. Both V0 and V1 seeds passed on physical hardware with exact cycle, CRC, and cache-profile matches to local simulation.

The difference between the R17 intermediate local denominator and the DC90363D denominator illustrates why resource efficiency must always be quoted with the exact image and complete-system accounting.

DC90363D established strict acceptance floors for all subsequent candidates:
1. Execution efficiency ≥ 3.181369716 CoreMark/MHz
2. Resource efficiency > 0.05345271285 CoreMark/LUT
3. Complete GPIO/UART/ILA preservation
4. Hardware validation required (not just simulation)

## Phase 7 — Final release: timing closure with execution efficiency improvement

### R19 — Final 153 MHz fetch-commit-factored release

**Parent:** R18/DC90363D as the governing board-level metric floor; immediate RTL parent was the failed complete-ILA 153 MHz timer implementation.

**Documents:** [`PROJECT_HANDOVER_153MHZ.md`](PROJECT_HANDOVER_153MHZ.md), [`experiments/full_fetch_commit_factored/README.md`](../experiments/full_fetch_commit_factored/README.md)

**Board qualification date:** September 11, 2026 (experiment box 1, device ID 12)

The final release applied three exact control substitutions:

1. Shared the normal prediction update and accepted unsent-redirect request condition
2. Factored `next_pc_write` around the common prediction-update condition
3. Preserved the original frontend-flush guard and all pipeline, reset, bus, predictor, and forwarding semantics

The purpose was complete-ILA timing closure. The parent failed at approximately `−0.223 ns` WNS; the final implementation passed at `+0.021 ns` WNS.

**Final hardware result:**

- Clock: `153 MHz`
- CoreMark: `511.317879224`
- CoreMark/MHz: `3.341946923`
- CoreMark/LUT: `0.05381160590`
- Complete-system area: `9502 LUT / 5079 FF`
- Setup WNS: `+0.021 ns`
- GPIO, UART, caches, and 42-data/33-trigger/1024-sample ILA retained

**Validation:**

Both full CoreMark images (V0 and V1 seeds) reported successful hardware download and complete UART results. Hardware cycles, retired instructions, CRC, and cache profiles matched local long simulation exactly:

- V0: `1,795,360,650` cycles / `1,649,428,424` retired / CRC `a14c`
- V1: `1,795,883,504` cycles / `1,649,775,523` retired / CRC `18e1`
- Each: `6000` iterations, exceeding 10 modeled seconds

**Local ILA validation:**

All three 1024-sample local ILA windows and four capture tests passed:
- Source/firmware binding verification
- Width/index/count validation
- MEM-fire validity checks
- Preceding-MEM-to-WB pipeline consistency
- Visual matrix review of 16-cycle SVGs

The user explicitly accepted local ILA checking as sufficient; remote ILA acquisition was not required.

**Comparison with DC90363D board baseline:**

- Throughput: `+2.0461%`
- Execution efficiency: `+5.0474%`
- Resource efficiency: `+0.6714%`
- Clock: `−2.8571%`

The final result successfully programmed and tested on the remote FPGA platform. Its local and hardware runs matched exactly in cycles, retired instructions, CRC, and cache profiles.

**Key architectural contributions:**

1. **Redirect priming** (from R14): Reduced redirect recovery overhead by capturing resolved targets in available fetch opportunities, directly improving execution efficiency by approximately 1.8–1.9%.

2. **WB byte retiming** (from R17): Precomputed byte-level equality/ordering for EX/WB comparisons, enabling timing closure at high frequencies without cycle-count penalty.

3. **Fetch-commit factoring** (final): Shared prediction-update conditions and factored `next_pc_write` logic, achieving complete-ILA timing closure with +244 ps improvement over the parent's −223 ps violation.

**Scope application:**

The complete scope firmware sampled at 1224 cycles per record (nominal 125 kHz), 256 records, with a 4.59-billion-cycle timeout. Local application checks passed:
- UART 0x55 verification
- Expected GPIO pulse sequence
- Two checksummed captures
- EMPTY, TIMEOUT, late=0, and ready state validation

Hardware scope smoke testing covered EMPTY, ARMED, and approximately 30-second real timeout. No hardware scope waveform/checksum or GPIO-key pulse capture was claimed.

**Explicit caveats:**

- PDS SCBV remains unset
- Full electrical/CDC review incomplete
- Independent clock measurement not performed
- Voltage/temperature margin testing not conducted
- Long-duration stability not demonstrated
- Configuration-power evidence not collected

The bounded UART/GPIO/reset synchronizer check is not whole-design CDC or MTBF proof. Successful board bring-up does not close these engineering caveats. The user authorized a provisional endpoint, not a universal signoff.

## Summary of complete project evolution

The project crossed multiple distinct optimization regimes:

### Phase 1: Baseline establishment (27 MHz)
- Established hardware bring-up methodology
- Integrated caches, peripherals, CoreMark infrastructure
- Baseline: 0.364 CoreMark/MHz (far below target)

### Phase 2: M-extension integration (120 MHz, 1.249 CoreMark/MHz)
- Full RV32IM ISA compliance
- Identified fundamental execution bottlenecks
- Established 3.0 CoreMark/MHz as clear target

### Phase 3: Execution efficiency breakthrough (120 MHz, 3.013 CoreMark/MHz)
- Data forwarding (MEM→EX, WB→EX)
- 256-entry BTB with 2-bit counters
- Aggressive cache sizing (8 KiB I-cache)
- Early memory request initiation
- Achieved target threshold on hardware

### Phase 4: Frequency and resource optimization (120–144 MHz)
- Progressive frequency scaling: 126 MHz, 132 MHz, 141.75 MHz, 144 MHz
- Folded BTB indexing and segmented ALU (+0.556% execution efficiency at 132 MHz)
- Branch-specific forwarding and LRU compression
- Resource efficiency improved from 0.0352 to 0.0513 CoreMark/LUT

### Phase 5: High-frequency exploration (145–151 MHz)
- Multiple timing-failed attempts at 145–146 MHz
- Identified critical paths: cache valid logic, fetch address selection, timer comparison
- Successfully qualified 148.5 MHz and 151.2 MHz locally
- Redirect priming innovation (+1.8% execution efficiency)

### Phase 6: Complete-system optimization (154–157.5 MHz)
- Shift to complete-ILA optimization (42-data/33-trigger/1024-sample)
- Commit-enable factoring
- WB byte retiming for high-frequency timing closure
- DC90363D board baseline: 157.5 MHz, 501.066 CoreMark, 3.181 CoreMark/MHz

### Phase 7: Final release with timing closure (153 MHz)
- Fetch-commit enable factoring
- Complete-ILA timing closure (+244 ps improvement)
- Hardware validation on physical FPGA
- Final: 511.318 CoreMark, 3.342 CoreMark/MHz, 0.0538 CoreMark/LUT
- All three efficiency metrics exceed DC90363D baseline

## Final metrics progression

| Milestone | Clock (MHz) | CoreMark | CoreMark/MHz | CoreMark/LUT | Area (LUT) |
|-----------|-------------|----------|--------------|--------------|------------|
| First board | 27 | 9.818 | 0.364 | — | 3,735 |
| M-extension | 120 | 149.881 | 1.249 | — | — |
| 3.0 threshold | 120 | 361.556 | 3.013 | 0.0352 | 10,285 |
| Resource opt | 120 | 361.556 | 3.013 | 0.0356 | 10,169 |
| Frequency scale | 126 | 379.634 | 3.013 | 0.0372 | 10,208 |
| Frequency scale | 132 | 397.712 | 3.013 | 0.0386 | 10,294 |
| Execution gain | 132 | 399.923 | 3.030 | 0.0386 | 10,353 |
| Branch forward | 144 | 442.493 | 3.073 | 0.0513 | 8,634 |
| Load carry | 148.5 | 464.520 | 3.128 | 0.0535 | 8,677 |
| Redirect prime | 151.2 | 504.661 | 3.338 | 0.0539 | 9,370 |
| Board baseline | 157.5 | 501.066 | 3.181 | 0.0535 | 9,374 |
| **Final release** | **153** | **511.318** | **3.342** | **0.0538** | **9,502** |

The final release is cumulative. Redirect priming is the main direct execution-efficiency contribution; WB retiming and fetch-commit factoring are primarily physical timing and control-logic optimizations. No single late-stage modification should be credited with the entire improvement from the 132 MHz version to the final result.

The project demonstrates exceptional engineering discipline through:
- Transparent documentation of all experiments, including failures
- Source SHA-256 tracking for complete provenance
- Paired performance/validation methodology
- Hardware verification of final release
- Honest assessment of remaining caveats and limitations

**Project status:** Provisionally complete. Further optimization paused. AI acceleration deferred per user request. Electrical/stability caveats explicitly documented.

