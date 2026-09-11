# Four-bit local-history screening experiment

Date: September 10, 2026. Parent: ../full_control_commit. Status: rejected at the tested physical point; not a replacement for the qualified parent or accepted hardware baseline.

## Hypothesis and exact change

The parent's timer-bounded V0 retirement profile groups 88.5954% of arithmetic extra interval cycles after conditional branches. That observation motivates predictor work, but is not a direct misprediction counter. See ../full_control_commit/EXECUTION_PROFILE.md.

Only rtl/rv32_btb.sv changes among the twenty physical inputs: default HISTORY_BITS=3 becomes 4. The predictor retains 256 entries and two-bit counters, increasing pattern banks from eight to sixteen. CPU, GPIO, UART, PLL, constraints and all other physical sources remain byte-identical to the parent. source-inputs.json records both sets of hashes. No firmware algorithm, seed, compiler optimization or timing function changes.

## Paired short RTL screening

| Seed | Parent run | Candidate run | Parent cycles | Candidate cycles | Saved |
| --- | --- | --- | ---: | ---: | ---: |
| V0 | 20260910-195856-6bf511dd | 20260910-212254-4ae1d8bd | 3060873 | 3053191 | 7682 |
| V1 | 20260910-195908-6ac62ce5 | 20260910-212306-26d37fed | 3065630 | 3060950 | 4680 |

Short-test throughput improves 0.251606% and 0.152894%. Firmware bytes, complete firmware metadata, retired counters and CRCs match each parent seed; speculative cache-access counts need not match. audit_short.py checks the actual one-line RTL delta, current inputs, source snapshots, normalized compile commands, executable, UART and parsed results. These ten-iteration tests are not official scores or evidence of ten timed seconds.

Eight actual RTL geometries pass across index widths 2/8, address widths 16/32 and hashing off/on. Each includes a directed sixteen-state four-bit-history sequence, repeated 32 times, in addition to the existing independent model vectors. Three compiled runtime mutants are rejected, including one that discards the fourth history bit. Six randomized-bus core/reference runs pass, each with thirteen traps. Nineteen candidate-specific firmware/wrapper/physical-auditor tests pass. External ISA and full peripheral/application requalification have not been repeated for this rejected experiment.

## Physical rejection

Both builds use configured 154285714 Hz, placement seed 2 and the unchanged V0 6000-iteration firmware. The ordinary and complete builds are separately preserved.

| Build | Post-route LUT | FF | Setup WNS | Result |
| --- | ---: | ---: | ---: | --- |
| build/pds/20260910-212508-0783b1a0 | 9142 | 4283 | -0.031 ns | Timing rejected |
| build/ila/20260910-history4-seed2 | 9663 | 5017 | -0.072 ns | Timing rejected |

Actual Inserter output and source-bound mapping audit confirm all 42 data channels, 33 trigger channels and depth 1024 in the complete build. The complete design has 257 more LUT than the parent's 9406, while the measured short execution benefit is small. Timing failure alone rejects this point; no long-run resource-efficiency claim is inferred from short tests. The full timing report lists twelve failing CPU setup endpoints. Its worst reported path starts at board/soc/core/mem_instruction[7]/opit_0_inv/CLK and ends at board/soc/core/mem_result[31]/opit_0_inv_L6Q_perm/I5; this is not evidence that a predictor counter path itself is the critical path.

Rejected complete bitstream SHA-256: 462124AD42C8A31A63661FB11B1CC68DF5693200B9FF9FE8DBB75E78738D2C9B. Its presence does not authorize programming. The native PDS process exits successfully after producing the file, but the separate timing qualifier rejects it. physical-qualification.json records physical_timing_passed=false and never grants hardware or score qualification.

The initial core regression could not locate the new directory's toolchain metadata. The existing verified compiler metadata was copied from the parent, and a fresh regression passed; no compiler rebuild was attempted. An initial full-ILA launcher attempt could not read the live synthesis log with File.ReadAllText. The native Get-Content read resolved the sharing issue before any ILA run had been created; the initial failed log and the fresh invocation remain distinct.

## Decision

Do not promote this version, run its rejected image on hardware, or upload it. The complete control-commit candidate and accepted DC90363D hardware baseline remain unchanged. The experiment supports investigating history accuracy with fewer counter banks rather than assuming a larger table improves the combined score/resource objective. Any subsequent design still needs independent RTL, full physical, long-run and eventual board qualification. No Chrome or GitHub action was taken.

