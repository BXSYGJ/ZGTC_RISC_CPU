# Return stack using the existing committed link value

## Full-ILA terminal results and external ISA verification

The ordinary build passes 151.2 MHz with 9127 LUT / 4354 FF / setup WNS +0.018 ns. Its bitstream SHA256 is 83180E782A7126655301A78E07CB75044A8B1F45C8DBD68576308E434797052E. Ordinary resources exclude ILA and are not an acceptance denominator.

Both complete-ILA attempts fail timing despite retaining the verified 42-data / 33-trigger / 1024-depth mapping:

| Placement seed | Full-system LUT | FF | Setup WNS |
| --- | ---: | ---: | ---: |
| 1 | 9452 | 5092 | -0.109 ns |
| 2 | 9558 | 5088 | -0.041 ns |

Seed 2 improves slack by 0.068 ns but costs 106 additional LUT. Neither image is promoted, and no long-run score is assigned. Seed-1 bitstream SHA256: 57BF8EA710E00D6C5EFFAAC9E002126A967887466863BDB477B3EEABE68FD5A4. Seed-2 SHA256: A839D258DC89E20BD78B68D9E78CA7B32F962C5FBB321476F140FAB14F7AB1C4. Sixteen audit tests cover source/firmware binding, actual native channels, register drivers, short UART results, regression completeness and link-observer integrity.

The seed-1 worst path starts at mem_result[28], traverses early branch comparison and ID issue control, and ends at raw_pair_relation[0].CE (ten levels, 2.060 ns logic, 4.205 ns routing). This measured path motivates the isolated ../full_raw_relation_payload experiment rather than an unbounded placement sweep.

Pinned external tests now pass: 41 RV32UI tests across four configurations (164 runs) and eight RV32UM tests across four configurations (32 runs), with four expected rejection controls per suite. run_external_isa.py captures the exact candidate RTL, adapters, archive provenance, compiler identity and artifacts; audit_external_isa.py rechecks them and every test/configuration pair. All four audit tests pass. Evidence: build/external-isa/audit.json and invocation.json. The supported behavior for ma_data is precise trapping, not transparent misaligned access. These are tests, not complete ISA certification; the external cache configurations use set bits 1/4, while the separate cached-core regression covers production set bits 6. This ISA evidence belongs to this exact link-reuse core, not automatically to later variants.

Earlier implementation-pending statements below are historical. The qualified local version and accepted board baseline remain unchanged.

## Synthesis comparison completed

The source-bound comparison reports predictor LUT 815 -> 786 and LUT-carry count 35 -> 8, with FF unchanged at 322. Inclusive core LUT drops 3989 -> 3950 and LUT-carry count 1198 -> 1165, with FF unchanged at 1749. Three parser tests pass. See build/synthesis-comparison.json for raw report hashes and source/firmware/wrapper binding. This establishes a synthesis hierarchy improvement only; nested totals must not be added and post-route full-ILA efficiency remains unqualified. It supersedes the older pending-arithmetic-removal statement below.

## Change and measured motivation

This isolated variant preserves the two-entry stack from full_return_stack2, which improves both short execution screens but fails its full-ILA timing gate (9669 LUT, WNS -0.205 ns at 151.2 MHz). The original stack's synthesis hierarchy adds 58 predictor LUT, 66 FF and 29 LUT-carry elements relative to the qualified parent. These hierarchy counts are not post-route LUT measurements.

The original stack explicitly computes update_pc+4. The core already produces ex_pc+4 as execute_result for JAL/JALR and registers it into mem_result. For a fault-free committed call, that register is the required pushed link address. This variant adds a stack_push_address input and connects it to mem_result instead of adding four inside the predictor. Commit qualification, two-entry capacity, overflow/underflow, x1/x5 hints, invalidation, tag matching, conditional prediction and fallback targets do not change. Added fanout or placement changes could offset the removed arithmetic; a physical benefit is not assumed.

Relative to the qualified full_redirect_clock151200 parent, only the CPU and predictor RTL change. GPIO, UART, caches, clock and constraints remain unchanged. Exact substitutions are recorded in change-receipt.json. CPU SHA256: 452A354CD13DEA3342386942A3A97F69B48587A7B5DC1CEE4F59B1210D8ACDB8. BTB SHA256: 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E.

## Verification completed

- Predictor tests pass 4123 vectors at each of depths 0/1/2/4/8, with disabled-stack equivalence and eight compiled fault rejections. Existing hit and direction outputs still match the qualified parent.
- Source-extracted hint/commit logic passes 32768 combinations and rejects four faults.
- observer-receipt.json proves that the two copied baseline benches add only link-value observation and coverage. Eight core/cache runs pass, with independent ISA trace and final-memory checks. Each observed run exercises three committed pushes and verifies mem_result == mem_pc+4 for them. This bounded check is not a formal invariant proof or exhaustive call/interrupt coverage.
- Both complete ten-iteration UART logs are byte-identical to full_return_stack2's corrected runs: V0 3000415 cycles, V1 3001205. The gains versus full_redirect_clock151200 remain 3925 and 6635 cycles, with unchanged retired counts and CRCs. No long-run score is extrapolated.

Evidence: build/test_return_stack.py.log, build/test_commit_gate.py.log, build/test_observer.py.log, build/core-regressions/manifest.json, build/v0 and build/v1. The screen reuses the same firmware, compiler commands and hardware parameters as the qualified parent, changing only the two RTL files.

## Physical status and remaining work

prepare_physical.py captures all twenty complete physical inputs and checks complete UART equality against the original return-stack candidate. Ordinary PDS run 20260911-035000-1d9fd437 starts at 151200000 Hz / seed 1 as PID 60528 in build/physical-project-complete. It uses the same V0 6000-iteration firmware. Final timing/resources and whether synthesis actually removes the extra arithmetic remain pending.

Native full-ILA 42-data / 33-trigger / 1024-depth mapping and implementation, paired 6000-iteration qualification, application integration and remaining board/electrical acceptance are still required. No resource-efficiency, frequency or board-score improvement is claimed. Neither the accepted local version nor the DC90363D board baseline changes. No remote-board access or GitHub upload occurs.
