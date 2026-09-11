# Shared raw operand relation experiment

## Candidate

Parent: the accepted DC90363D source at `build/regfile-valid-fanout-stage`.
Only `rtl/rv32_core.sv` changes. UART, GPIO, FIFO, caches, PLL and constraints are copied byte-for-byte; no UART experiment is included.

The original CPU computes `operand_relation` separately on EX operand refresh and ID issue. This candidate uses one call with existing `compare_next_a/b` operand selection, retaining the original EX-or-ID capture condition and reset. ID issue remains higher priority. No pipeline stage, ISA capability or cache capacity is removed.

The RTL expresses a shared comparator, but successful sharing and area/timing benefits require actual synthesis and implementation evidence. Operand-selection fanout or added control depth could negate the area saving.

## Verification

- `python test_shared_relation.py`: exact source-delta guard, 32768 source-extracted sequential comparisons with four-state operands/controls and 16 reset cycles, six runtime mutation rejections.
- The initial test report is preserved in `build/relation-regression-initial-test-errors.json`. One expected-diff newline was wrong, and unconditional refresh was incorrectly classified as an erroneous mutation: recomputing held operands produces the same relation. Neither issue is hidden as a CPU failure or a successful negative control.
- `scripts/run_core_tests.ps1 -BtbIndexBits 8 -EarlyDRequest`: all six predictor/seed runs and independent ISA trace/final-memory checks pass. These run the actual changed CPU, not merely UART/peripheral benches.
- `scripts/run_cached_tests.ps1 -BtbIndexBits 8 -ICacheSetBits 9 -CacheSetBits 6 -EarlyDRequest -DataOverlap -LoadUseBubble -FastICacheHit -FetchOverlap -FastDCacheRead -FastDCacheWrite`: both predictors pass, 9584 and 9568 checks, with independent trace/memory validation.
- Simulation tools ignore some existing synthesis attributes; that warning is not proof of physical attribute behavior.

## Acceptance gates

Ordinary PDS run: `build/pds/20260910-151146-f2a68b53`, 157.5 MHz, placement seed 2, exact V0 performance firmware hash `0E5EAD297589F9689CE8D9D60163DD7DD87FD71FF7EC11731545DE9CD9E99ABF`.
Ordinary results exclude ILA and cannot use 9374 full-system LUTs as their comparison denominator.

To promote: retain GPIO/UART and actual 42-data/33-trigger/1024-depth ILA; pass full-system timing at 157.5 MHz; improve complete-system resources without losing execution efficiency; complete both CoreMark workloads and hardware validation. No inherited scores, baseline replacement, or GitHub push.

## Terminal ordinary implementation result (2026-09-10)

- Baseline ordinary source: 8996 post-route LUT, 4281 FF, WNS -0.157 ns.
- Shared candidate: 8823 post-route LUT, 4290 FF, WNS -0.482 ns at configured 157.5 MHz.
- Same-configuration area saving: 173 LUT; setup slack worsens by 0.325 ns. Both ordinary runs fail timing, so neither supplies a new accepted score.
- The comparison audit rechecks all 20 captured inputs, the exact three CPU edits, unchanged top-level parameters, identical firmware, raw reports, bitstream hashes and regression source hashes. Run `python audit_ordinary_result.py`; its output is `build/ordinary-comparison-audit.json`.

The candidate worst setup path starts at D-cache `request_address_1_copy[6]`, traverses tag/hit and `ex_fire_without_irq` control, then `compare_next_a[28]`, and ends at `raw_pair_relation[0]`. It has eight logic levels, 1.980 ns logic and 4.365 ns routing. This directly exposes the late operand-selection cost of this sharing structure.

Directly instantiated synthesis-core primitives are recorded separately in `build/core-primitive-comparison.json`; they are not post-route LUT counts and do not prove full combinational equivalence.

This candidate is not promoted or programmed. Full ILA has not been inserted, and full CoreMark execution efficiency is unmeasured for it. Do not sweep this structure blindly or quote 8823 against the complete 9374-LUT baseline. Preserve parallel comparison on late-control paths in a future area-sharing design.
