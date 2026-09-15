# Exact fetch-commit enable factoring

## September 11, 2026 — final local ILA and hardware acceptance

This experiment is now the provisionally accepted complete version: **153 MHz, 511.317879224 hardware CoreMark, 3.341946923 CoreMark/MHz, 0.053811605896 CoreMark/LUT**, 9502 LUT / 5079 FF and +0.021 ns setup WNS. Both 6000-iteration hardware seeds exactly match their local timed cycles, retired counts, CRCs and cache profiles. All three 1024-sample local ILA windows and four capture tests pass. The user explicitly accepts local ILA checking; no remote ILA acquisition is required or claimed.

The full scope image passes hardware EMPTY/ARMED/real-time TIMEOUT smoke checks; complete waveform/checksum tests remain local evidence. The device is released. Further optimization is paused. The source-bound configuration is recorded in `configuration.json` and `change-receipt.json`. SCBV, electrical and long-term stability caveats remain explicit. The older local receipts are intentionally unchanged. All older running-state entries below are historical.


## September 11: own long pair and complete application locally qualified

This entry supersedes all older running-state paragraphs below. Both 6000-iteration RTL runs and both complete native ILA images are terminal and pass their source-bound audits. The latest locally metric-qualified candidate is full_fetch_commit_factored; no board-baseline replacement is claimed.

| Metric | Current local result |
| --- | ---: |
| Configured and timing-passing clock | 153 MHz |
| CoreMark projection | 511.3178792238763 |
| Execution efficiency | 3.341946923031871 CoreMark/MHz |
| Resource efficiency | 0.05381160589600887 CoreMark/LUT |
| Complete post-route area | 9502 LUT / 5079 FF |
| Setup WNS | +0.021 ns |

The area denominator is the larger complete-system count across the performance and validation images; both are 9502 LUT. GPIO, UART and all 42 data / 33 trigger / 1024-depth ILA functions remain present. Against accepted DC90363D, the local projected score increases 2.0461%, execution efficiency 5.0474% and resource efficiency 0.6714%, while clock decreases 2.8571%. These compare a local projection to the accepted board baseline, not two board measurements.

Relative to the preceding locally qualified full_redirect_clock151200 candidate, score increases 1.3190% and execution efficiency 0.1270%, but resource efficiency decreases 0.0885%. This remains above the explicit accepted-board resource floor; it is not a claim of Pareto improvement over every intermediate candidate.

Performance run build/compiled/20260911-102437-50412c5f measures 1795360650 timed cycles, 1649428424 retired instructions and CRC a14c. Validation run build/compiled/20260911-105001-2a7db72e measures 1795883504 timed cycles, 1649775523 retired instructions and CRC 18e1. Both use 6000 iterations, pass the CRC checks and exceed ten modeled seconds. The total simulation limits and terminal cycles are separate from the timed benchmark interval; the failed earlier watchdog run remains preserved and rejected.

Joint receipt: build/local-joint-score-resource-qualification.json, SHA256 909D8E616A1F57D6D6EC4EE9E847D3EE67D67B48842BDF9F8DBB4342A19C200E. It records local_pair_validated=true, local_metric_gates_passed=true, hardware_validated=false, full_score_qualified=false and baseline_replaced=false. Seven joint-audit methods and two long-boundary methods pass, including role/source/firmware/clock/ILA/denominator rejection controls and actual terminal-log validation.

### Full application

The unchanged scope software is rebuilt for 153 MHz, sampling every 1224 cycles and using a 4590000000-cycle timeout. Its firmware hash is 4D6AF10D6117FEC061273512E0AABF36B7916B357BFE66E152C89C6E3A388B06. The source-bound full-CPU simulation build/scope-current/20260911-105053-71d3ebca passes in 2700386 cycles with two captures, decoded UART 0x55, the expected GPIO pulse sequence, EMPTY, TIMEOUT, no late samples and the ready LED state. The timeout test deliberately uses two 64-bit counter jumps; it does not simulate thirty continuous seconds.

Ordinary scope image build/pds/20260911-105255-fc9be582 passes at 9075 LUT / 4321 FF / +0.018 ns. Full-ILA scope image build/ila/fetch-commit-scope-seed1 passes at 9502 LUT / 5079 FF / +0.021 ns and preserves all ILA channels. Bitstream SHA256 D2D91235C09FF5C5D7E9639AA6887AF8642FFEA82B4AA441D580711C7CEEFF6F. The application and benchmark share all twenty physical sources and hardware parameters; firmware roles are explicit and cannot be interchanged. Eight preparation, four role-separation and four runtime-audit methods pass.

Application receipt: build/local-application-qualification.json, SHA256 D24CB9F0D11ACB6D6A3FAE38E8014DF0B212CFBC7D2C3B4AB8B3D72B2F16EB42. It establishes local application qualification, not board or electrical acceptance.

### Next optimization and remaining gates

Both source-bound, nonintrusive ten-iteration retirement profiles reproduce their original UART, cycles and CRC exactly. Conditional-branch-adjacent intervals account for 88.485% / 89.331% of arithmetic retirement-gap overhead in the two seeds. These are correlations, not direct misprediction counters. EXECUTION_PROFILE.md records the evidence and prioritizes general-purpose branch prediction/redirect recovery rather than removal of working peripherals or benchmark-specific shortcuts. Four profile negative-control methods and both independent replay audits pass.

All three current synthesized input netlists pass the bounded four-chain synchronizer check; six positive/negative methods pass. LOCAL_ELECTRICAL_REVIEW.md records the explicit limits. PDS still reports unset SCBV; actual board configuration-power evidence, complete electrical/CDC acceptance and board measurements remain open. Browser port 19476 is untouched. No Git operation or GitHub upload occurs.

### Reproduction

From this experiment directory, use audit_fetch_long.py and audit_fetch_joint.py to recheck the paired long/full-ILA metrics. audit_fetch_application.py takes build/scope-current/20260911-105053-71d3ebca. audit_fetch_async.py --include-application checks the three current input netlists. audit_fetch_profile.py takes a completed build/retirement-profile directory. Do not rebuild fixed physical stages or restart completed simulations merely to reproduce an audit.


## V1 implementation and corrected long-run completion bound

V1 ordinary run 20260911-101436-c57addf3 is terminal and passes with the same 9075 LUT / 4321 FF / +0.018 ns as V0. Its bitstream SHA256 is A4B09895E954940BF36D91B31F16406DECCAD0E721708CC02E7F56A692B44FCB. Four firmware-role tests pass, including rejection of swapped roles and non-Boolean role values and an unchanged hash for the existing V0 mapping receipt. V1 complete ILA stage build/ila/fetch-commit-v1-seed1 verifies the actual 42 / 33 / 1024 mapping and is running as native PDS PID 94340, execution session 6555. Its final timing/resource result is not yet available.

The initial long V0 simulation 20260911-100607-a0d609db terminates at the selected 2100000000-cycle watchdog while printing the first performance-result line. No trap is reported; final CRC/output and status completion are absent, so the attempt is not accepted. This is an actual simulated-cycle limit failure, not a tool observation timeout. Its original UART, executable, source snapshot, manifest and logs remain intact; the serial runner stops before launching V1.

The earlier qualified full_redirect_clock151200 long manifests and full_id_relation_mask1 long auditor require a 6000000000-cycle overall limit, covering startup, the timed benchmark, the configured pauses and complete result output. run_long.ps1 now uses that verified predecessor limit, and audit_fetch_long.py requires the same bound. No CPU, firmware, benchmark interval or clock parameter is changed to address the watchdog.

The fresh completion attempt is build/compiled/20260911-102437-50412c5f, owned by execution session 92529; the actual Vrv32_soc process and MaxCycles=6000000000 were verified live. V1 waits behind V0 in the same serial runner. The two short/incomplete-long rejection tests pass again after this change. Do not restart either live handle merely because an observation expires. No candidate long score, execution/resource-efficiency value, full-project completion or board result is claimed.

## Complete 153 MHz V0 image passes timing

The complete fetch-commit-seed1-native-wb implementation is terminal and passes all reported timing constraints at configured 153 MHz: 9502 total post-route LUT, 5079 FF, setup WNS +0.021 ns. Bitstream SHA256: 5BBBEA849F5E3E51576927641FC7DC00393862D6BD9CB3638C3769E7FF757DB1. The 42-data / 33-trigger / 1024-sample ILA, GPIO and UART are retained.

Relative to the immediately preceding failed 153 MHz timer implementation, full-system LUT use is unchanged at 9502 and setup slack improves by 0.244 ns; physical FF count rises by 13 although RTL state is unchanged. The worst reported path is ex_operand_b[1] -> next_pc[11].CE with 10 logic levels, 2.169 ns logic and 3.822 ns routing, compared with the parent's 11-level / 2.110 ns logic / 4.170 ns route path. This is a measured implementation improvement, not a new execution-efficiency claim or proof of a global timing optimum.

All eleven original actual-stage ILA binding/mapping/qualification methods pass (nine mapping methods plus two terminal-qualification methods), as do the five WB alias rejection tests. Two long-run boundary tests reject short UART and incomplete pairs. The source-bound current external ISA run passes 164 RV32UI and 32 RV32UM executions across four configurations, plus eight expected rejection controls. Five provenance/coverage tests pass. The misaligned-data case is an expected precise trap rather than transparent-misalignment support; this remains bounded upstream coverage, not exhaustive ISA certification. External invocation SHA256: 87BD07F8FABE1E5010F770A56DF0F2B763FECB9BB0F475625CE99725835B3437.

V1 ordinary implementation starts at build/pds/20260911-101436-c57addf3, PID 90384 / execution session 18553, with the same twenty physical inputs and only validation firmware changed. The ILA adapter now accepts an explicit --validation role, checks the corresponding fixed firmware manifest and does not silently mix V0/V1 images. Its role-extension tests are tracked separately in build/validation-binding-tests.log. After V1 ordinary completion, its complete ILA command is run_full_ila.ps1 -SourceRun 20260911-101436-c57addf3 -RunName fetch-commit-v1-seed1 -ValidationRun; do not launch another native implementation concurrently.

Own long V0 is still tracked by execution session 25772; V1 is queued in the same serial runner. No candidate long result or new resource-efficiency value is assigned before the actual pair and corresponding physical images are validated. Existing metric floors, application evidence, electrical/SCBV review and board-acceptance gates remain in force. Earlier running-state paragraphs are historical.

## Ordinary timing passes; complete ILA and long runs in progress

Ordinary run 20260911-095312-74f93c4b is terminal and passes at configured 153 MHz: 9075 post-route LUT, 4321 FF and setup WNS +0.018 ns. Synthesis uses 8505 LUT versus the parent's 8565, but synthesis counts are not the full-system metric denominator. Ordinary bitstream SHA256: F212E077BECB8E52830D58F949B21277E819A399A1044442C1E19B6B41F66577. SCBV/electrical acceptance is still open.

The first ILA stage fetch-commit-seed1 stops before native implementation because Inserter removes the unavailable original WB-valid net from channel 36. Actual net discovery locates board/soc/unused_pipeline_valid[4]. The new adapter proves its direct core output connection to the synthesized wb_valid register Q; it does not substitute another event or omit a channel. Five alias-proof/rejection tests pass and the incomplete first stage remains rejected and preserved.

Corrected stage build/ila/fetch-commit-seed1-native-wb passes actual Inserter verification of all 42 data / 33 trigger channels and depth 1024. Core-local IF/ID, SoC EX/MEM aliases, and the WB output alias are bound to their actual registers and probe results. Native PDS runs as PID 94504 / execution session 71356. Nine actual-stage mapping/binding tests and six source/functional/short-evidence audit methods pass. The two terminal physical-qualification tests must wait for the full implementation result; no full-system timing or resource pass is claimed yet.

Own 6000-iteration V0/V1 simulations are launched serially in execution session 25772, using unchanged parent 153 MHz firmware and max_cycles=2100000000. V0 build is build/compiled/20260911-100607-a0d609db; its UART confirms the 6000-iteration start. The V1 command waits for V0 completion. audit_fetch_long.py requires the actual completed pair, current captured sources/commands/executables/raw UART, CRC validation and at least ten modeled seconds. It does not inherit a parent score or claim resource/hardware qualification. Preserve the existing simulation handle.

## Scope and measured motivation

This isolated complete-system candidate starts from full_timer_clock153000 at configured 153 MHz. The parent full-ILA implementation is timing-rejected at 9502 LUT / 5066 FF / WNS -0.223 ns. Its worst path crosses ex_operand_b[20], early branch condition, frontend flush, i_req_valid and next_pc_write before reaching next_pc[14].CE: 11 levels, 2.110 ns logic and 4.170 ns routing.

Only rtl/rv32_core.sv changes, through three exact substitutions in change-receipt.json. Parent CPU SHA256: 707941FBAF4B5E73EDF3380022C4EA32D109446BA78D3B8CA6608DCAF131065B. Candidate CPU SHA256: EC22FD905CF50FCEC84981EED57835615CC3C62E2B046F41E5052A026A623DB8. All other nineteen physical inputs, hardware parameters, firmware, PLL and constraints stay unchanged. GPIO, UART, caches, interrupts and the required 42-data / 33-trigger / 1024-sample ILA remain mandatory.

## Exact enable transformation

An overlapped accepted request already implies the normal prediction/next-PC update condition. Its contribution to the union of write enables is therefore redundant. The new shared fetch_prediction_update combines normal capture with accepted unsent redirect requests. next_pc_write adds frontend_flush; prediction capture adds its original !frontend_flush guard. Two identical prediction assignments become one assignment with exactly the same effective enable.

No reset, state register, forwarding choice, bus event, predictor operation or pipeline timing is changed. Unlike the older full_fetch_prediction_payload experiment, this does not allow extra writes to dead payloads: every prediction register value must remain equal cycle by cycle. The Boolean argument does not depend on assuming pending implies unsent.

## Completed checks

- Five functional test methods pass in build/fetch-tests-e9c9a259, with fifteen compiled runs and preserved source, command, executable and log hashes.
- The actual parent and candidate enable equations agree on all 256 input combinations in each overlap mode: 512 combinations and 1024 enable comparisons total, including otherwise unreachable combinations.
- Four 6000-cycle randomized dual-core runs cover both predictor and overlap modes. All prediction payloads, fetch controls, bus events, live pipeline metadata and retirement agree. Each observes 388 flushes and barriers; held responses number 312 or 417, with 949 simultaneous transfers in each overlap-enabled run. No extra payload writes occur.
- Four directed suites each pass 35 cases / 444 checks, including request backpressure, stale responses, redirect replacement, barriers and reset.
- Five compiled capture/enable faults are rejected at runtime. FATAL output in those negative-control logs is expected, not a candidate failure.
- Sixteen core/cached selftest runs pass independent instruction-trace and final-memory comparison across predictor and load-bubble modes, retaining forwarding, trap and interrupt checks. These bounded tests do not claim complete external ISA certification.
- Both ten-iteration CoreMark runs are byte-identical to the parent UART: 3000565 / 3001255 cycles, 2748941 / 2749614 retired instructions, CRC fcaf / c64e. Builds: 20260911-094801-420d3685 and 20260911-094810-8ee47390. There is no measured execution-efficiency gain from this timing-focused transformation.

Source/input, functional-run, exact-command, executable and raw-UART auditors pass. The first functional-output audit needed Windows path normalization; it did not change any tested source, output inventory, assertion or simulation result.

## Physical workflow and acceptance boundary

Ordinary PDS starts at build/pds/20260911-095312-74f93c4b (PID 61048, execution session 46921), using the unchanged 153 MHz V0 6000-iteration firmware, seed 1 and complete physical-source snapshot. Inspect the existing process and terminal artifacts; do not restart after an observation timeout. Complete native ILA probing, register-driver binding, timing and total LUT evaluation follow serialization with this run. Timing and resources are not yet qualified.

No candidate long-run score, new board measurement, resource-floor pass, electrical/SCBV closure or accepted-baseline replacement is claimed. The existing local qualified 151.2 MHz version and DC90363D board baseline remain unchanged. All five non-AI tasks, application and analysis obligations remain open as applicable. No GitHub or browser action is taken.
