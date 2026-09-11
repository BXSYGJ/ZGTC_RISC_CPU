# Pending-fetch acceptance simplification

Parent: ../full_redirect_prime. Only rtl/rv32_core.sv changes physically, to remove i_req_valid from the deferred-prediction acceptance predicate. GPIO, UART, memory, PLL, constraints and full 42-data/33-trigger/1024-depth ILA remain required. The accepted hardware baseline and locally qualified full_control_commit candidate are not replaced.

## Invariant and verification

fetch_redirect_pending implies fetch_active && !fetch_sent && !fetch_discard, which implies i_req_valid. Reset clears pending; a redirect creates it only in a free or simultaneously drained slot; request acceptance, barriers and subsequent redirects clear it. This removes a logically redundant input from the commit enable under the invariant, without intentionally changing execution cycles.

The actual RTL passes 288 one-step invariant-state/control combinations per overlap setting, covering nine binary invariant states and 32 control patterns. The controls are isolated for this bounded check, so it is not whole-core formal verification. Twenty-four live RV32I reference-core comparisons cover predictor, fetch-overlap and load-use-bubble modes with three randomized bus seeds; all outputs are compared cycle by cycle, with an independent architectural trace check. Four directed fetch-FSM modes (35 scenarios, 444 checks each) and six rejected RTL mutants also pass.

## Execution screen

V0 20260910-230309-3456598d and V1 20260910-230321-0d85a2ff retain exactly 3004340 / 3007840 timed cycles. Retired counts, CRCs and cache profiles are identical to the parent. audit_short.py verifies firmware, compilation settings, snapshots and the exact CPU substitution. This is not an additional execution gain or a long-run score.

## Physical status

Source implementation: build/pds/20260910-230437-872a1ac3. Full ILA: build/ila/20260910-redirect-accept-seed2-remapped. The first Inserter stage is retained as a rejected mapping: synthesis exposed ID-valid at board/soc/unused_pipeline_valid[1], and the full map cannot silently omit it. The corrected mapping proves the signal through its native register Q and core output connection before accepting actual Inserter output. Twenty-seven audit test methods pass. The ordinary build fails at -0.275 ns (9098 LUT / 4283 FF). Full ILA fails at -0.532 ns (9481 LUT / 5020 FF); this is worse than the parent seed-2 physical result, despite preserved execution. The simplification is not promoted.

Long V0/V1 simulations 20260910-231803-b547d994 and 20260910-231828-3483fd63 use a 6000000000-cycle limit. The earlier parent attempt stopped at an insufficient 2500000000 cycles during paced output and is not a score. Four long-duration guard tests pass; the new runs remain unqualified until all output and CRC checks complete.

## September 11 completed long-run audit

Both new 6000-iteration runs complete with final CRC a14c / 18e1 and timed cycles 1797640625 / 1799846469. The matched source-bound audit in build/long-comparison.json verifies firmware, RTL substitutions, executable and outputs, retired counts and modeled durations of 11.651374 / 11.665672 seconds. Performance execution efficiency projects 3.337708280819477 CoreMark/MHz, and 514.9607052299455 CoreMark at configured 154285714 Hz. Four duration guard tests pass again.

The existing full-ILA -0.532 ns timing failure still rejects this implementation; the long simulation is not a board score or a physical qualification. These measurements are not transferred to the different 151.2 MHz redirect-prime candidate, which runs its own firmware and long pair.

Version updates are recorded in ../../docs/ACCEPTANCE.md. No browser, remote-board programming or GitHub operation is performed.
