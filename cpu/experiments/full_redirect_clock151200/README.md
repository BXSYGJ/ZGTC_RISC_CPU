# Redirect priming at 151.2 MHz

Latest optimization follow-up: CONTROL_EVENT_PROFILE.md records the completed internal-event diagnosis and two paired predictor-correlation screens. Both variants preserve correctness but increase cycles; neither replaces this qualified candidate. The full-system metrics below remain unchanged.

## Application and algorithm analysis completed

Scope runtime 20260911-010153-3367fed2 now completes successfully at 2693243 cycles: two 256-sample captures, UART 0x55, GPIO transitions 0/1/0, zero late samples, EMPTY and counter-jump timeout checks. audit_scope_run.py and the new audit_application.py bind its current sources, parameters and firmware to the separately passing full-ILA scope image. build/local-application-qualification.json records local_application_pair_passed=true but hardware_validated=false and electrical_qualified=false. The earlier decoder-failure manifest is unchanged.

Three current-core 1024-cycle algorithm windows have completed and passed source/ELF/firmware/output and temporal-transfer audits. WB events are 736 for list, 483 for matrix and 563 for state; these are local window counts, not global IPC. The complete observed short-run result is unchanged. Full and zoom SVGs are under build/ila-pipeline-rtl/redirect-prime151200; the matrix zoom and UART waveform preview were rendered and visually checked. These are RTL-only observations of the physical ILA logical channel set, not DebugCore-RAM or remote-board captures.

The latest completed local metric result remains 151.2 MHz, 3.337708280819477 CoreMark/MHz and 0.053859284104579 CoreMark/LUT, with 504.6614920599049 CoreMark and 9370 full-system LUT. The current analysis is experiments/full_redirect_clock151200/PERFORMANCE_REPORT.md (relative to cpu); its application and artifact details supersede earlier pending-status entries. Twelve joint-binding, seven application-pair, four pipeline, eight decoder, three scope-runtime and four exact-floor regression methods pass. The actual current pair is included, not only an older fixture.

The five non-AI tasks, complete task/documentation closure and continued optimization remain active. Electrical/board-configuration evidence is still open; no remote access or GitHub upload is performed. Next optimization work should distinguish branch/dependency causes in the remaining branch-following retirement gaps while preserving the full system and both baseline floors.

## Completed local metric qualification

The candidate-specific 6000-iteration pair has completed: V0 20260911-001254-0e98e281 takes 1797640625 cycles with CRC a14c; V1 20260911-001315-6a0c1e04 takes 1799846469 cycles with CRC 18e1. Both exceed ten modeled seconds. audit_long.py and audit_joint.py validate current and captured sources, firmware, compiler configuration, complete output and paired full-ILA physical images. build/local-joint-score-resource-qualification.json records both metric floors passing. These are RTL-derived projections, not board scores.

| Metric | This candidate | DC90363D board baseline | Change |
| --- | ---: | ---: | ---: |
| Configured clock frequency | 151.2 MHz | 157.5 MHz | -4.0000% |
| Execution efficiency | 3.337708280819477 CoreMark/MHz | 3.181369715697977 | +4.9142% |
| Resource efficiency | 0.053859284104579 CoreMark/LUT | 0.053452712846429634 | +0.7606% |
| Throughput guard | 504.6614920599049 CoreMark | 501.0657302224314 | +0.7176% |

Both benchmark images use 9370 full-system LUT / 4986 FF with +0.017 ns setup slack and retain GPIO, UART and all 42 data / 33 trigger / 1024-sample ILA functionality. Versus the previous locally qualified full_control_commit, throughput decreases about 0.1502%, but execution and resource efficiency improve; the governing DC90363D throughput and resource floors both pass. No highest-achievable-frequency claim is made.

The scope full-ILA image 20260911-redirect-clock151200-scope-seed1 also passes at 9370 LUT / 4986 FF, WNS +0.017 ns; bitstream SHA256 C2A21D376B9F0FD48AC0D8B107CE2E053D1FFCD2C6884352A13637C09A81B7CE. Runtime 20260911-004616-9388dcd0 reaches the actual testbench PASS at 2693243 cycles, but host postprocessing fails because the decoder clock allowlist omitted 151200000. Its original incomplete manifest is retained. The decoder now accepts that exact clock, passes eight regression methods, and correctly decodes both saved raw captures (UART 0x55, GPIO transitions 0/1/0, sample period 1210, zero late samples). A fresh end-to-end run 20260911-010153-3367fed2 is in progress; saved-data reanalysis is not substituted for its completion receipt.

Electrical/configuration-power evidence, complete local task acceptance and eventual board validation remain open. The hardware baseline is not replaced, Chrome 19476 is untouched, and no GitHub upload occurs. Earlier sections below are historical progress entries.

This isolated experiment retains all twenty physical source inputs from full_redirect_prime, including GPIO, UART and the required 42-data / 33-trigger / 1024-sample ILA. Only the build clock changes from 154285714 Hz to 151200000 Hz. The existing PLL selects input divide 1, multiplier divide 2, feedback divide 14 and output divide 5. No feature is removed to improve area.

The parent improved paired short-run cycle counts but failed full-ILA timing at 154285714 Hz with all three tested placement seeds. Earlier operand-selector experiments did not provide a clear joint advantage. This candidate tests whether a modest clock tradeoff preserves the execution gain while meeting both the 501.0657302224314 CoreMark and 0.053452712846429634 CoreMark/LUT floors. That outcome is not assumed from short tests or estimated timing.

Firmware, local RTL tests, both full-ILA implementations and long-duration scores require this clock configuration and source-bound evidence. No parent score is relabeled as a candidate score. No timing, resource, hardware or complete acceptance claim is made at creation. Version updates are recorded in ../../docs/ACCEPTANCE.md.

## Initial verification

Six clock/source/firmware test methods pass, including actual PLL parameter elaboration and a rejected wrong-ratio RTL mutant. Thirteen firmware mutations, four configuration changes and four physical-source hash changes are rejected. These checks establish the selected configuration, not analog PLL behavior or measured oscillator frequency.

Clock-specific short runs 20260910-233631-e15b5716 / 20260910-233649-cc01ef34 pass. The source-bound paired audit verifies identical RTL, normalized compilation commands, retired counts, cycles, CRCs and cache profiles versus the parent; only clock-specific firmware settings change.

The first full-ILA run 20260910-redirect-clock151200-seed2 passes actual Inserter verification of 42 / 33 / 1024, then terminates with native PDS exit 1 during placement: memory allocation failed for 1048512 bytes. There is no timing result or qualified bitstream from that attempt. Its input hashes and failure logs are retained. A fresh retry must wait for the concurrent ordinary implementation to finish; no running implementation is overwritten or restarted.

## September 11 follow-up

Ordinary PDS completes with 9072 LUT / 4290 FF and WNS -0.026 ns. The serialized full-ILA seed-2 retry completes with 9399 LUT / 4998 FF and WNS -0.159 ns; its bitstream SHA256 is C0F1C2B0B47E3B54AB358044E10BC7F6D853989CADB59FE296AFE3C1BBE1FC05. Both fail timing. Actual ILA and artifact audits do not promote either image. The next full-ILA seed-1 run is serialized after the completed retry and rechecks available commit headroom.

The source-bound retirement observer and paired-stream comparison pass; exactly 56533 intervals improve by one cycle and none worsens versus full_control_commit. Six comparison/provenance test methods pass. See EXECUTION_PROFILE.md for the measured remaining branch-heavy gaps and evidence boundaries.

## Passing performance-image placement

Full-ILA seed 1 (20260910-redirect-clock151200-seed1) passes native timing at +0.017 ns with 9370 LUT / 4986 FF, all 42 / 33 / 1024 ILA dimensions and source-bound artifact checks. Bitstream SHA256: ED45D1C8D1678E0C70C671AEAC086415CA4D7EBFD66FBD8AD7A3EA4453D7B556. SCBV/electrical acceptance remains open. This is not a complete paired score or board result.

Candidate-specific long simulations 20260911-001254-0e98e281 / 20260911-001315-6a0c1e04 use 6000000000-cycle limits. Validation-firmware PDS starts as 20260911-001344-ee795aac; full-ILA validation seed 1 is serialized after the ordinary run. No score is borrowed from full_redirect_accept, whose completed long runs use a different clock and CPU predicate.

## Paired physical images and application integration

Validation full-ILA stage 20260911-redirect-clock151200-v1-seed1 now also passes with 9370 LUT / 4986 FF and +0.017 ns setup slack. Its bitstream SHA256 is 1C93B95632E9B6DB6F01C72D0968840F37500718F7CFDAB8F8E6AFEC46F31B23. The first launcher attempt fails before stage creation because PowerShell splats a scalar string into characters; the typed-array fix passes two native argument tests before the actual implementation starts. Both physical images preserve the complete ILA and remain distinct from pending long-run and board qualification.

Scope firmware is rebuilt for 151200000 Hz, 1210-cycle sampling and a 4536000000-cycle timeout, SHA256 72BE13E1AABEDFBEDF7EA2DE4A97DC49ECA020FDB2158DA64582ADF89C32655E. Six application-firmware and six long-binding tests pass. The first runtime attempt hits a 600-second host timeout; its incomplete artifacts are retained. A fresh diagnostic run streams progress and UART, and three logger tests ensure timeout/failure diagnostics survive. This logging change does not change RTL or firmware and does not itself prove application correctness.

Ordinary scope PDS is 20260911-003942-efd1764f; the scope full-ILA stage is serialized after its verified process. Application completion, long-run metric qualification, SCBV/electrical review and remote-board validation remain open.
