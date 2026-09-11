# Free-slot redirect priming

Parent: ../full_control_commit. This is an isolated, unqualified full-system experiment. The accepted hardware baseline is unchanged.

## Functionality contract

GPIO, UART and the complete ILA remain required. Optimization may change implementation structure, not remove peripheral behavior, observation signals, trigger capability or capture depth. ILA retains 42 data channels, 33 trigger channels, 1024 samples and the CPU clock. Resource efficiency must use the complete post-route system, including ILA, rather than the ordinary build without ILA. Source hashes confirm that the CPU is the only changed physical input; GPIO/UART, memory, PLL and constraints are byte-identical to the parent.

## Redirect implementation

On a redirect, an idle or simultaneously drained instruction-fetch slot captures the redirect target immediately. Prediction is deferred until that registered request is accepted, while next_pc retains the target so the existing BTB lookup sees the correct address. Outstanding requests keep their address and drain with discard asserted. Repeated redirects and FENCE.I barriers cancel pending prediction metadata; reset clears the added state. The external request address remains registered. This removes a recovery allocation cycle when the slot is available without deleting system functionality.

## Local execution screen: September 10, 2026

Both comparisons use identical firmware bytes, hardware parameters, clocks and normalized compilation commands. Only the CPU RTL differs.

| Seed | Parent cycles | Candidate cycles | Cycles saved | Throughput change |
| --- | ---: | ---: | ---: | ---: |
| V0 | 3060873 | 3004340 | 56533 | +1.8817% |
| V1 | 3065630 | 3007840 | 57790 | +1.9213% |

Candidate builds: 20260910-221841-e6c87093 and 20260910-221854-55aa843e. Both have valid CRCs and unchanged retired counts. These ten-iteration RTL runs take less than ten modeled seconds and are not official scores, hardware results, or proof of the score/resource floors. audit_short.py verifies source snapshots, executable, firmware, UART and result hashes, and writes build/short-comparison.json.

## Verification

- Four directed fetch-FSM modes pass 35 scenarios and 444 checks each; six faulty RTL mutations are rejected. These tests force redirect/predictor control inputs and do not prove the entire pipeline.
- Six randomized core tests pass with independent architectural reference traces, predictor off/on and early data requests.
- Twenty-four physical-binding, evidence-integrity, qualification and ILA-alias test methods pass. Negative tests reject missing or miswired pipeline channels, reduced ILA width/depth and altered peripheral RTL in simulation snapshots.
- The first Inserter stage rejected obsolete synthesized aliases before implementation. Its evidence is retained at build/ila/20260910-redirect-prime-seed2. The corrected fresh stage is build/ila/20260910-redirect-prime-seed2-remapped.
- The corrected mapping proves pipeline bits 0..3 from the actual if_valid/id_valid/ex_valid/mem_valid native register Q connections. Inserter confirms all 42 data and 33 trigger channels. No signal is dropped or replaced by a constant to make the mapping pass.

## Physical qualification

Ordinary PDS build 20260910-222004-7326e2e2 has 9094 post-route LUTs, 4295 FFs and setup WNS -0.250 ns at 154285714 Hz: timing fails. That build excludes ILA and must not supply the complete-system resource denominator. The full-ILA seed-2 build uses 9406 LUT / 5004 FF and fails timing at -0.450 ns. Alternate full-ILA placements also fail: seed 1 has 9416 LUT / 5004 FF at WNS -0.238 ns; seed 3 has 9335 LUT / 4984 FF at WNS -0.613 ns. The placement-comparison.json receipt verifies identical RTL, firmware, constraints and functional ILA settings. No smaller-LUT result is accepted without timing closure. No candidate hardware qualification or promotion is granted. Configuration-power/electrical requirements must still be resolved before remote programming.

Run test_redirect_prime.py under WSL Python with Icarus. Run the other test modules with Python unittest from this directory. run_full_ila.ps1 requires an explicitly fresh RunName after the retained initial alias rejection; the corrected run uses 20260910-redirect-prime-seed2-remapped. It uses the existing licensed Windows PDS installation and actual source binding.

No browser access or GitHub upload was performed.

The current-clock scope application passes in build/scope-current/20260910-224857-b5792441: 2705484 cycles, two waveform dumps, UART 0x55, KEY, no late samples, EMPTY and timeout checks. The bench accelerates UART timing and jumps the cycle counter across 2^32; it is not a physical 30-second measurement. Inputs and resulting executable/UART logs are hash-verified.

Version status is recorded in ../../docs/ACCEPTANCE.md. External RV32UI/UM passed 164 + 32 runs with four rejection controls per suite; two GPIO configurations, fourteen precise M cases and external-UART SoC/fault tests also pass. Seed parameterization adds two negative/positive tests; it does not change the tested CPU source.
