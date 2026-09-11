# 选题一需求与验收账本

## Provisional endpoint — September 11, 2026

The latest user stopping criterion supersedes continued optimization: local ILA checks suffice, followed by remote hardware bring-up, a human document, an AI handoff and the explicitly authorized GitHub snapshot. Remote ILA acquisition is not required because of platform limitations. AI acceleration remains deferred.

`experiments/full_fetch_commit_factored` passes the validation gates at 153 MHz: hardware V0 = 511.3178792238763 CoreMark, 3.341946923031871 CoreMark/MHz and 0.05381160589600887 CoreMark/LUT using 9502 complete post-route LUT / 5079 FF, WNS +0.021 ns. V0/V1 each use 6000 iterations and report 1795360650 / 1795883504 timed cycles, 1649428424 / 1649775523 retired instructions and a14c / 18e1 final CRC; all match source-bound local runs. Device 12, Experiment box 1 PG2L200H, reports successful programming for all three complete images and is released.

Three source-bound local ILA windows each pass 1024 samples / 42 logical channels / 1023 temporal checks; four capture tests pass. Native physical mapping preserves 42 data / 33 trigger / 1024 depth. No physical DebugCore RAM acquisition is claimed. Five new hardware packet negative-control methods pass. Scope hardware smoke verifies EMPTY, ARMED and a real approximately 30-second TIMEOUT; full scope waveform/checksum qualification remains local. Hardware help truncation is recorded rather than hidden.

Final evidence: `docs/evidence/153mhz-20260911/`; raw local hardware: `build/hardware/fetch-commit153000-20260911-box1/`. Human guide: `docs/PROJECT_HANDOVER_153MHZ.md`; continuation document: `docs/AI_HANDOFF_153MHZ.md`. Fresh-clone archive verification: `python cpu/scripts/verify_153mhz_handoff.py` from repository root. The legacy printed 545 value is not the accepted score; use the exact cycle-derived calculation.

This is provisional user-scope acceptance, not complete electrical/CDC, environmental or official competition certification. SCBV remains unset, clock is configured rather than independently measured, and long-duration stability remains unproven. Historical local-only receipts are not rewritten into hardware results. Further optimization stops after this one authorized publication; subsequent pushes require another user request. Earlier active/running paragraphs below are historical.


## Active requirements — September 10, 2026

The latest user objective supersedes the historical metric thresholds and stripped-system comparison rules below. Preserve GPIO, UART, all 42 ILA data channels, all 33 trigger channels and 1024-sample depth. Evaluate resource efficiency using the complete post-route system. CoreMark must remain at least 501.0657302224314 and CoreMark/LUT at least 0.053452712846429634; execution efficiency remains an optimization objective rather than a separate nondecreasing gate. Clock tradeoffs are allowed.

AI acceleration remains deferred; the five other tasks, application scenario and analysis deliverables remain in scope. Existing local-PDS/RTL ILA acceptance does not become a remote-ILA requirement. The user supplied Chrome debugging port 19476, but remote-board verification must wait until the project satisfies its local requirements.

The isolated `experiments/full_control_commit` candidate has passed both complete ILA implementations and both 6000-iteration RTL runs at 154285714 Hz and 9406 total LUT. Its local projection is 505.4205959278995 iterations/s, 3.2758742389324493 iterations/(s * MHz), and 0.0537338503006485 iterations/(s * LUT). See its README and `build/local-joint-score-resource-qualification.json`. These are not board scores; the accepted DC90363D baseline is unchanged. Application integration and remaining electrical/constraint acceptance must not be inferred from the numerical result.

September 10 application update: the same candidate now also has a qualified full-ILA scope application image at `experiments/full_control_commit/build/ila/20260910-control-commit-scope-seed2-retry1`, with 9406 LUT, 5004 FF and setup WNS 0.000 ns at configured 154285714 Hz. Actual Inserter verification retains 42 data / 33 trigger channels and depth 1024. The source-bound application simulation and physical-image checks pass; neither is board validation. The bounded synthesized synchronizer review passes, but the actual remote board configuration-power/SCBV evidence and complete electrical review remain open; see `experiments/full_control_commit/LOCAL_ELECTRICAL_REVIEW.md`. Browser port 19476 remains untouched under the user's pre-qualification gate.


## Fetch factoring: 153 MHz long pair and full application qualified locally

September 11: experiments/full_fetch_commit_factored now has its own completed 6000-iteration performance/validation pair and complete native ILA images. The source-bound joint receipt passes both explicit DC90363D metric floors: **511.3178792238763 CoreMark**, **3.341946923031871 CoreMark/MHz**, **0.05381160589600887 CoreMark/LUT**, at **153 MHz / 9502 complete post-route LUT / 5079 FF / +0.021 ns**. GPIO, UART and 42 data / 33 trigger / 1024-depth ILA are retained. Resource efficiency is 0.6714% above the accepted board baseline, although it is 0.0885% below the preceding 151.2 MHz local candidate; score and execution efficiency improve over both. This meets the explicit baseline-floor policy, not a stronger all-intermediate-candidates Pareto rule.

Own performance run 20260911-102437-50412c5f records 1795360650 timed cycles / 1649428424 retired / CRC a14c; validation run 20260911-105001-2a7db72e records 1795883504 / 1649775523 / CRC 18e1. Both exceed ten modeled seconds. Their actual simulation terminals are 4681722617 and 4679545823 total cycles under the 6000000000-cycle completion limit. The incomplete earlier 2100000000-cycle watchdog result remains rejected. Session 92529 work is terminal by the completed manifests and actual PASS logs; no restart is needed.

Joint receipt: experiments/full_fetch_commit_factored/build/local-joint-score-resource-qualification.json, SHA256 909D8E616A1F57D6D6EC4EE9E847D3EE67D67B48842BDF9F8DBB4342A19C200E. local_pair_validated and local_metric_gates_passed are true; hardware_validated, full_score_qualified and baseline_replaced remain false. Seven joint-audit methods and two long-boundary methods pass. The accepted DC90363D board result is unchanged.

The same CPU now has an independently qualified full application: 153 MHz scope firmware with 1224-cycle sampling and a 4590000000-cycle timeout; full-CPU simulation 20260911-105053-71d3ebca passes in 2700386 cycles with two captures, UART 0x55, GPIO pulse sequence, EMPTY/TIMEOUT, zero late samples and the ready LED state. The 64-bit timeout test uses explicit counter jumps, not thirty continuous simulated seconds. Ordinary scope PDS 20260911-105255-fc9be582 passes at 9075 LUT / 4321 FF / +0.018 ns. Full-ILA scope stage fetch-commit-scope-seed1 passes at 9502 LUT / 5079 FF / +0.021 ns, bitstream D2D91235C09FF5C5D7E9639AA6887AF8642FFEA82B4AA441D580711C7CEEFF6F.

Application receipt: experiments/full_fetch_commit_factored/build/local-application-qualification.json, SHA256 D24CB9F0D11ACB6D6A3FAE38E8014DF0B212CFBC7D2C3B4AB8B3D72B2F16EB42. Eight preparation, four firmware-role and four runtime-audit methods pass. The role extension preserves both existing benchmark mapping receipts and rejects application/benchmark swaps. GPIO, UART and the full ILA are never removed to obtain these numbers.

Further execution-efficiency work is now guided by two independently audited, observer-only retirement traces, each exactly matching its original short-run UART/cycles/CRC. Conditional-branch-adjacent intervals contain 88.485% / 89.331% of arithmetic gap overhead; this is not direct internal misprediction attribution. See experiments/full_fetch_commit_factored/EXECUTION_PROFILE.md. Four profile negative-control methods pass. The next targeted investigation is general-purpose branch prediction/redirect recovery rather than additional load-use or peripheral stripping.

The three current synthesized input netlists also pass the bounded four-chain synchronizer audit and six regression methods; see experiments/full_fetch_commit_factored/LOCAL_ELECTRICAL_REVIEW.md. Actual board configuration-power/SCBV, complete electrical/CDC acceptance and board verification remain open. The user's remote-board gate is still in force; Chrome port 19476 is untouched and nothing is pushed to GitHub. Older running-state entries below are historical and superseded.

## Fetch factoring: V1 ILA running; long completion watchdog corrected

September 11: V0 complete-system timing remains passed at 153 MHz / 9502 total LUT / +0.021 ns with GPIO, UART and the full 42-data / 33-trigger / 1024-depth ILA. V1 ordinary run `20260911-101436-c57addf3` is collected and also passes at 9075 LUT / 4321 FF / +0.018 ns; bitstream SHA256 A4B09895E954940BF36D91B31F16406DECCAD0E721708CC02E7F56A692B44FCB. Four explicit firmware-role tests pass, including unchanged V0 mapping bytes and rejection of swapped V0/V1 roles. V1 full-ILA stage `fetch-commit-v1-seed1` passes actual 42 / 33 / 1024 mapping and runs as PID 94340 / session 6555; final physical metrics remain pending.

Initial long V0 `20260911-100607-a0d609db` reaches the actual 2100000000-cycle watchdog while printing the initial performance-result line. No trap is reported, but complete UART/CRC/status evidence is missing, so the run remains rejected. Session 25772 is terminal and V1 was not started by that failed serial attempt. All failed artifacts are retained. This is a terminal simulation watchdog, not an expired tool observation.

The previously qualified local long-run manifests and parent long auditor use 6000000000 total simulation cycles. The new `run_long.ps1` and long auditor use that verified bound to allow startup, timed execution, pauses and complete result output. No RTL, clock, benchmark source, firmware or timing interval is modified. The fresh V0 attempt `20260911-102437-50412c5f` is verified live under session 92529 with MaxCycles=6000000000; V1 is queued behind it. Short/incomplete-long rejection tests pass again. Preserve both live handles rather than restarting on an observation timeout.

No new own execution-efficiency or resource-efficiency result is yet qualified. Both baseline metric floors, all five non-AI tasks and the application/electrical/SCBV/board gates remain active. No GitHub or browser action is performed. This entry supersedes earlier notes that described session 25772 as running.

## Complete fetch factoring passes at 153 MHz; own metric pair still pending

September 11: `full_fetch_commit_factored/build/ila/fetch-commit-seed1-native-wb` is collected and passes native timing at 153 MHz with 9502 complete-system post-route LUT, 5079 FF and WNS +0.021 ns. All 42 data / 33 trigger channels and 1024 samples are actually verified; GPIO/UART remain present. Bitstream SHA256: 5BBBEA849F5E3E51576927641FC7DC00393862D6BD9CB3638C3769E7FF757DB1. Compared with its failed 153 MHz parent, total LUTs are unchanged and slack improves by 0.244 ns. The worst path is ex_operand_b[1] -> next_pc[11].CE, 10 levels / 2.169 ns logic / 3.822 ns routing. No execution-efficiency improvement is inferred from this timing result.

Eleven actual-stage ILA methods pass, including both terminal qualification tests; five WB alias tests, six prerequisite audit methods and two long-run boundary tests also pass. The current CPU passes 164 RV32UI plus 32 RV32UM executions and eight rejection controls from the pinned local archive. Five actual-provenance/coverage tests pass; invocation SHA256 is 87BD07F8FABE1E5010F770A56DF0F2B763FECB9BB0F475625CE99725835B3437. This is bounded external coverage, not exhaustive ISA/electrical certification.

V1 ordinary PDS is running at `build/pds/20260911-101436-c57addf3`, PID 90384 / session 18553. Its explicit validation firmware is 9ECD2172E0412543BB5D55E386D77549B8817F7602ACD2F0D0591F7306BD1FE5. The ILA adapter gains separately tested explicit firmware-role binding while preserving the existing V0 mapping. The long-run serial session 25772 owns V0 `20260911-100607-a0d609db`, with V1 queued. Do not restart these handles on observation timeouts.

No new own long-pair score, resource efficiency, baseline promotion, application/electrical/SCBV closure, board validation or GitHub publication is claimed. Both metric floors and all five non-AI tasks remain active. This terminal V0 physical entry supersedes the earlier pending-state notes.

## Fetch factoring: ordinary timing passes; full ILA and long pair running

September 11: `full_fetch_commit_factored` ordinary run `20260911-095312-74f93c4b` is collected and timing-passes at 153 MHz with 9075 LUT / 4321 FF / WNS +0.018 ns. Bitstream SHA256: F212E077BECB8E52830D58F949B21277E819A399A1044442C1E19B6B41F66577. Ordinary counts still exclude the required ILA and cannot establish the resource floor. Six source/functional/short-evidence audit methods pass.

First ILA attempt `fetch-commit-seed1` stops at a missing native WB-valid alias before implementation. The actual discovered SoC pipeline_valid[4] alias is proven through the CPU output port to wb_valid.Q; five dedicated tests reject missing probes, wrong ports/drivers and the original incomplete verification output. The corrected `fetch-commit-seed1-native-wb` stage passes actual 42-data / 33-trigger / 1024-depth verification and nine mapping/binding tests. Its native PDS PID is 94504, execution session 71356. No live process is restarted.

Own 6000-iteration runs start serially in session 25772; V0 is `build/compiled/20260911-100607-a0d609db`, with V1 waiting behind it. `audit_fetch_long.py` is prepared for the actual source-bound pair rather than inherited performance. Full-system timing, total LUTs, long-run metrics, application/current external ISA coverage and electrical/SCBV acceptance remain pending. Both metric floors and all five non-AI tasks remain active; no baseline, browser or GitHub update is made.

## Exact fetch-commit factoring: functional checks pass; physical build started

September 11: new `full_fetch_commit_factored` changes only three CPU source fragments relative to the complete 153 MHz timer parent. An overlapped request already implies the normal capture enable; the redundant handshake dependency is removed from next-PC and prediction write-enable unions. Prediction capture remains cycle-exact, unlike the earlier relaxed dead-payload experiment. No state, reset, GPIO, UART, cache, interrupt, predictor or ILA requirement is removed. CPU SHA256: EC22FD905CF50FCEC84981EED57835615CC3C62E2B046F41E5052A026A623DB8.

Five functional methods / fifteen compiled cases pass: 512 exhaustive Boolean combinations, four 6000-cycle exact-state dual-core runs, four 35-case redirect suites and five runtime mutation rejections. Sixteen core/cached runs pass independent trace/final-memory comparison across predictor and load-bubble modes. Both short CoreMark UARTs match the parent byte-for-byte at 3000565 / 3001255 cycles and CRC fcaf / c64e. These are bounded local functional checks, not a new long score or full external ISA certification.

The source-bound input, functional-output, command and short-UART audits pass. Windows functional-output paths are normalized without weakening the exact inventory. Ordinary PDS runs at `build/pds/20260911-095312-74f93c4b`, PID 61048 / session 46921, at actual configured 153 MHz / seed 1. Complete native 42-data / 33-trigger / 1024-depth ILA follows after this process terminates. Preserve the existing process rather than restarting on a timeout. Both metric floors, all five non-AI tasks and application/electrical/SCBV acceptance remain mandatory. No new metric, board, baseline-promotion or GitHub claim is made.

## Complete 153 MHz timer system: terminal timing rejection

September 11: `full_timer_clock153000` ordinary run `20260911-091937-b10d286c` completes with 8938 LUT / 4310 FF / WNS -0.049 ns. Complete native ILA stage `timer-clock153-seed1` completes with 9502 post-route LUT / 5066 FF / WNS -0.223 ns at configured 153 MHz. Actual discovery and synthesized register-driver binding retain all 42 data / 33 trigger channels and 1024 samples. The native process and wrapper are collected; no timeout-driven restart occurs. Bitstream SHA256: 141163A197322937E0DB7A2ABB1C198869B58B12C4E16A19FCC91D8C34053965.

Eleven clock-specific ILA audit methods pass on real artifacts and rejection controls. They check the correct 153 MHz parser input, complete source/firmware binding, actual channel drivers/probe uniqueness and invocation completion/inventory. The real timing failure stays rejected; no long score or resource efficiency is inferred from short results or inherited performance. This supersedes the pending-state entry below.

The limiting path is ex_operand_b[20] -> early condition -> frontend flush -> i_req_valid -> next_pc[14].CE, with 11 levels, 2.110 ns logic and 4.170 ns routing. A focused exact-enable factoring experiment follows. The existing qualified local 151.2 MHz metric version and accepted DC90363D board baseline remain unchanged. GPIO, UART, complete ILA, both metric floors and all five non-AI tasks remain mandatory; application, electrical/SCBV and eventual board acceptance are not waived. No GitHub or browser action occurs.

## Complete timer system at 153 MHz: paired short tests pass; ordinary PDS running

New `experiments/full_timer_clock153000` preserves every physical source file from full_timer_prefix16. Only the configured clock, firmware clock constant and narrow tool/parser clock whitelists change. GPIO, UART, caches, interrupts and all 42-data / 33-trigger / 1024-sample ILA requirements remain intact. The existing PLL source already supports the 153 MHz setting.

Three source-input tests, two firmware-audit tests, four strict result-parser tests and three short-evidence audit tests pass (twelve total). All four V0/V1 short/6000-iteration firmware images are built with unchanged pinned sources and compiler options apart from the clock constant. The source-bound short pair passes at 3000565 / 3001255 cycles, CRC fcaf / c64e and unchanged retired/cache statistics. The initial missing-header and parser-whitelist failures are retained and documented; no failed attempt is promoted.

Ordinary PDS 20260911-091937-b10d286c is active at the actual configured 153 MHz (launch PID 85748), using long V0 firmware SHA256 6DAAE1B97ED63CBD65BFF5A8F6BD15FC4E67378BA3316D790911EF5CF5D545CD. No 153 MHz full-ILA result or new long score is yet available. The clock choice is motivated by the conditional 152.68333357284476 MHz requirement at the parent 9546-LUT area, not by treating estimated Fmax as a validated clock. All acceptance gates and the previous baseline remain unchanged.

## Parallel timer prefix: complete ILA passes with 107 fewer LUT

The complete relation-reuse implementation now identifies the timer increment/compare path as its worst setup path (16 levels, 2.439 ns logic and 3.583 ns routing). New `experiments/full_timer_prefix16` retains the exact relation-reuse CPU and all complete-system functions while replacing only the 64-bit timer increment with four parallel 16-bit chunks and combinational prefix carries. No counter register, interrupt latency, GPIO/UART function or ILA channel is removed. Peripheral SHA256: AB2D42B769C2493630325E3DB9CB2D5447608F20EF57D884D64A9D2F1B7E2D3E.

Three functional methods pass the complete peripheral differential suite, 57 bus-driven carry-boundary cases, 512 partial writes and four compiled faulty-module rejections. The positive run has 58536 checks and observes all 16/32/48-bit carries plus 64-bit wrap. Three staging-audit tests pass. The first short screen rejects an implicit carry-operand width warning before PDS. The corrected source explicitly zero-extends the carry to 16 bits and passes all functional and staging tests again. Both corrected short runs pass with UART byte-identical to the parent at 3000565 / 3001255 cycles and CRC fcaf / c64e. Seven ILA binding tests pass. Ordinary PDS 20260911-084958-ea943cd6 is terminal at **151.2 MHz / 9119 LUT / 4327 FF / WNS -0.065 ns**, rejected for timing. The critical path now runs through EX operand comparison/control rather than the timer. The full-system denominator remains pending. Original rejected artifacts remain preserved.

Four native-netlist tests and a source-bound audit confirm the maximum consecutive timer carry chain decreases from 63 to 17 cells; this is not total routed path depth. Global synthesis LUT decreases 8727 -> 8633, inclusive peripheral LUT 732 -> 711, with unchanged total FF. The first ILA attempt exposes a changed MEM-valid alias and stops before implementation. A native probe proves core-local pipeline-valid nets, and the corrected timer-prefix16-seed1-native-core stage passes actual 42/33/1024 Inserter mapping and ten binding/native-mapping tests. Full-ILA PDS is terminal and passes at **151.2 MHz / 9546 total LUT / 5076 FF / +0.106 ns setup WNS**, saving 107 full-system LUT against relation reuse. Bitstream SHA256: CC44051D358026C55969C52CB49A4D75D3A32A8E6D70BCFB2BC5F2474FEAE928. The worst full-system path is now MEM-result-to-fetch-prediction control, not the timer. No new paired long score is claimed.

At the parent complete area of 9653 LUT, the resource floor requires 515.9790371065852 CoreMark. Reusing the parent execution efficiency would imply at least 154.39474324100883 MHz, but neither that execution efficiency nor that clock is assigned to this child without its own evidence. Remaining CPU paths and actual placement also limit frequency. The accepted baseline remains unchanged; no remote-board or GitHub action is performed.

## Forwarded-relation reuse: complete timing pass, no resource qualification

New `experiments/full_relation_reuse1` changes only the EX relation refresh in the CPU (SHA256 707941FBAF4B5E73EDF3380022C4EA32D109446BA78D3B8CA6608DCAF131065B). It reuses the existing early relation only with load bubbles enabled and preserves the original comparator for bubble-disabled direct MEM-load forwarding. Higher-priority ID capture, reset, all peripherals and complete ILA functionality remain unchanged.

Sixteen independent-reference core/cache configurations pass, including both load-bubble and predictor modes. Three live parent-comparison/fault-test methods pass eight compiled cases. Both short UART runs remain byte-identical to the parent at 3000565 / 3001255 cycles. The pinned external ISA audit passes 196 positive runs plus eight rejection controls, with four audit tests. These are functional screens, not a new long-run score.

Ordinary PDS 20260911-082214-6a099604 passes at **151.2 MHz / 9191 LUT / 4339 FF / +0.235 ns setup WNS**. Native synthesis drops 26 total LUT and 44 carry cells, with 42 more LUT7 multiplexers and unchanged total FF; nested resource counts are not additive. The ordinary LUT count is not the required complete-system denominator.

The first ILA attempt stops before implementation because the MEM-valid core-local alias is not exposed by Inserter. A native net probe and checked SoC-port/register-Q connectivity identify board/soc/unused_pipeline_valid[3] as the correct net. The corrected relation-reuse1-seed1-native-alias stage passes actual 42-data / 33-trigger / 1024-depth verification and twelve binding/native-mapping tests. Its native PDS implementation is terminal at **151.2 MHz / 9653 full-system LUT / 5055 FF / +0.108 ns setup WNS**. The bitstream SHA256 is FBD3D625F5A928BCF88EFD4616FBE9F97101BC8FEDC634E7E40B928F8BD8E52E. Full-system area increases by 21 LUT versus the immediate parent, despite lower synthesis area. No new long-run score or joint metric qualification is asserted. See the candidate README for retained initial harness failures and evidence paths.

The accepted board baseline and latest locally metric-qualified full_redirect_clock151200 remain unchanged. All five non-AI tasks, application/analysis deliverables, full GPIO/UART/ILA and metric floors remain active; SCBV/electrical evidence is still open. No browser or GitHub operation is performed.

## Banked peripheral read decoder: complete implementation rejected

New `experiments/peripheral_read_banks` retains the complete peripheral module and changes only its read-data/error decode structure. All 26 read addresses, GPIO, UART, timer/software/external interrupts, response backpressure and nine snapshot words remain present. The complete source snapshot differs from full_id_relation_mask1 only in rv32_peripherals.sv, SHA256 ACA515C9557035BCDDDB11C92BE50ED32E7F710795FDC56F4E52CDEAE1D1B9B2. No task or ILA function is removed.

Three source-bound functional methods pass 105281 reference-versus-candidate cycles, 55803 checks, all 2048 low offsets, 10752 high-bit alias reads, sixteen snapshots and five compiled fault rejections. Both full-SoC short UART logs are byte-identical to the parent: 3000565 / 3001255 cycles, CRC fcaf / c64e. Ten binding/native ILA mapping tests and three staging tests pass. These short runs are not a new score.

Ordinary PDS 20260911-074734-14aad077 is terminal at **9207 LUT / 4352 FF / WNS -0.009 ns** at 151.2 MHz, and is rejected for timing. Synthesis total LUTs fall 8753 -> 8709 but the peripheral hierarchy remains 733 LUT; no final resource improvement follows from those synthesis counts. Full ILA peripheral-read-banks-seed1 starts only after the previous native process terminates, as PID 89184. Actual Inserter verifies 42 data / 33 trigger / 1024 samples and the native pipeline register drivers. Complete-system implementation is now terminal at **9579 total LUT / 5056 FF / WNS -0.071 ns**, four failing setup endpoints and TNS -0.119 ns. Bitstream SHA256 F2A5D4C236BE4B249BBE3273D9BB7F442828D7245E8F9056B0121AAC4554E0CA. The 53-LUT reduction is real for these matched complete images, but timing fails and the candidate is rejected. The worst path is MEM result bit 24 through early branch comparison/control to I-cache RAM address, nine levels with 1.737 ns logic and 4.826 ns routing.

The latest locally metric-qualified version and accepted board baseline remain unchanged. Parent long scores cannot be assigned to this new peripheral RTL. The next structural investigation is reusing the already-computed forwarded relation rather than building another EX comparator. The original load-forwarding behavior must remain available. No browser, board programming or GitHub operation occurs.

## Completed paired measurement and metadata rejection

The current completed-result audit supersedes the earlier running/pending statements below. `full_id_relation_mask1/audit_long_pair.py` binds both successful 6000-iteration RTL runs to their own source/firmware-matched, timing-passing 42-data / 33-trigger / 1024-depth physical images. Ten new paired-auditor methods and all existing long/physical audit methods pass (59 total). V0 is 1795360650 cycles / CRC a14c; V1 is 1795883504 cycles / CRC 18e1. Both modeled intervals exceed ten seconds.

At 151.2 MHz and 9632 complete post-route LUTs, V0 projects **505.3023747624189 CoreMark**, **3.341946923031871 CoreMark/MHz**, and **0.05246079472201193 CoreMark/LUT**. The source-bound pair is locally validated but the exact resource floor fails; the new joint receipt records local_metric_gates_passed=false, hardware_validated=false and baseline_replaced=false. At unchanged score, at most 9453 LUTs are allowed: the next area target is a reduction of at least 179 LUTs. No board score is claimed.

`full_return_history1` is also terminal, not pending: ordinary 9228 LUT / 4320 FF / WNS +0.076 ns; full ILA **9633 LUT / 5058 FF / WNS -0.004 ns**, three failing endpoints, TNS -0.012 ns. All ILA dimensions and 196 pinned ISA runs plus eight rejection controls pass, but timing fails and full area increases by one LUT. Its bitstream is 3B8DD00AAAF60055A22890B2B8663EF832367C3CD659EE6E50FF6363CBEF7DBC. The 25-LUT synthesis reduction does not translate to routed-area savings. No long score is assigned to this rejected child.

The latest locally metric-qualified version remains `full_redirect_clock151200`; accepted board baseline DC90363D is unchanged. GPIO, UART, full ILA, application and electrical requirements remain in scope. No browser or GitHub operation occurs.

## Return-history metadata integrated into a complete candidate

New full_return_history1 retains the full_id_relation_mask1 CPU unchanged (SHA256 D37866F5E7EBB3D64D581C4C73B663EC742038C597B29953ABF1BF2AA53BE86B) and integrates only the tested predictor metadata representation (BTB SHA256 6E1B86520A18A36CBC8F5AE4ADA3568207660851EE794C8178879F5C44FB2030). Twenty-four source-bound safety methods, six safety-auditor methods and eight core/cache independent-reference comparisons pass. Eighteen UART/trace/memory files are byte-identical to the immediate parent; short cycles remain 3000565 / 3001255. GPIO, UART and full 42/33/1024 ILA requirements remain unchanged.

Actual native synthesis confirms removal of return_entry_0/1, two GTP_RAM128X1DP cells whose data input was update_return. Predictor RAM128X1DP count falls from 20 to 18, and ordinary synthesis total LUTs fall from 8753 to 8728. The captured source sets differ only in rv32_btb.sv. These are synthesis results, not complete post-route area or resource efficiency.

Ordinary PDS 20260911-071234-398f5b87 starts as PID 22800 at 151.2 MHz. Full-ILA implementation is queued after the verified process; native discovery already confirms core-local IF/ID/EX/MEM valid signals. Final ordinary/full-ILA timing/resources and pinned independent ISA results remain pending. The parent long simulations remain live and untouched; no parent score is assigned to this candidate. No qualified baseline replacement, remote-board access or GitHub upload occurs.

## Return metadata storage experiment: differential checks pass

While the timing-passing full_id_relation_mask1 long runs continue, isolated `experiments/return_history_metadata` removes the dedicated return_entry array and stores return classification in history bit zero only for unconditional entries. Conditional history and allocation/type-transition rules remain unchanged; every unconditional training event refreshes the flag. Four source substitutions produce BTB SHA256 6E1B86520A18A36CBC8F5AE4ADA3568207660851EE794C8178879F5C44FB2030. This is a storage optimization experiment, not a new integrated CPU or measured LUT improvement.

Three methods pass: exact delta, five 12000-cycle reference-versus-candidate configurations (24000 output comparisons each), and five compiled fault rejections. Configurations cover index widths 4/8, history widths 1/3/4 and stack depths 0/1/2. Checks include conditional-history preservation, encoded return classification, type transitions, collisions, invalidation/reset, unaligned updates and stack-based target selection. Actual complete-system area/timing and integrated CPU regressions are still required; the ongoing parent long runs and V1 build are unchanged.

## ID relation mask factoring: both full images pass, long measurements running

New `full_id_relation_mask1` targets the rejected decode-payload full-ILA path from register-valid selection through ID comparison. Three exact substitutions compute the raw relation before late validity selection, reusing the existing raw register/WB muxes. Original operand masks, reset/initialization, x0 semantics, forwarding and pipeline priorities remain unchanged. CPU SHA256 D37866F5E7EBB3D64D581C4C73B663EC742038C597B29953ABF1BF2AA53BE86B; BTB unchanged. No peripheral or ILA requirement is removed.

The new combinational test passes 32768 cases with all source-index pairs, validity combinations, four WB routes, signed boundaries and masked X/Z register payloads; six compiled faults fail the intended result checks. This does not prove arbitrary unknown-control equivalence. Twenty-one source-bound safety methods, six safety-auditor methods and eight core/cache independent-reference comparisons pass. Both short UART logs plus sixteen trace/memory files match the immediate parent byte for byte. V0/V1 remain 3000565 / 3001255 cycles with fcaf / c64e CRCs. The initial strict-attribute diagnostic failure and ambiguous inherited mutation-anchor failure are retained separately; corrected complete evidence is build/safety-final.

Ordinary PDS 20260911-063921-2a052d9e completes at 9211 LUT / 4317 FF / WNS +0.023 ns. Complete V0 ILA id-relation-mask1-seed1 passes at **9632 total LUT / 5029 FF / WNS +0.052 ns** at 151.2 MHz; all 42 data / 33 trigger channels and 1024 samples are verified by native Inserter and 21 audit tests. Bitstream SHA256 97E7FA282A6DE2CC6838292502117ECCE4F05A24F1CAAACE1336CEC1759BFC3F. The full-image worst path moves to MEM result bit 4 through control into fetch_prediction[27].CE, ten levels with 1.951 ns logic and 4.177 ns routing.

All 196 pinned ISA runs and eight rejection controls complete successfully, with four coverage-auditor tests; invocation SHA256 6C76168627F6D8BDDFB18D809F8A3BBCCDA52CA041221A65A0059200595672A0. Seven new long-run gate tests pass. Both 6000-iteration RTL measurements start in build/long-v0 and build/long-v1, with unchanged long reference firmware and compiler/model settings, source/output binding and a 7200-second timeout. Neither long run is complete at this entry. Separate V1 ordinary PDS 20260911-065629-53494b7b completes at 9211 LUT / 4317 FF / WNS +0.023 ns. Fresh native discovery, actual 42/33/1024 V1 mapping and 21 V1 audit tests pass. V1 full-ILA run id-relation-mask1-v1-seed1 also completes at 9632 LUT / 5029 FF / WNS +0.052 ns. Its bitstream SHA256 is C8521F5826DC1D10BB02A12020645D29BFC1911594CD2ACFC03D010AD4EB8709. Both physical images pass; both long simulations remain incomplete.

At 9632 full-system LUT, matching the baseline resource efficiency requires at least 514.8565301368102 CoreMark (3.40513578132811 CoreMark/MHz at 151.2 MHz). This is the acceptance threshold, not an estimated score. Passing V0 timing does not establish that threshold. Full paired metrics, application/electrical acceptance and eventual board checks remain open; no qualified baseline replacement, board access or GitHub operation occurs.

## Decode payload candidate: full-ILA timing rejection

New `full_decode_payload1` starts from `full_mul_prefetch_valid1`, retaining the one-entry return stack, guarded raw multiplier prefetch, GPIO and UART. Two exact substitutions allow ID payload capture on empty-ID, empty-EX or EX consumption while preserving all valid/flush/barrier priorities. CPU SHA256 A5FBA551C3D6FFA7924E396F44F458D34008E0D89898F519A74F16EEC8E7C45D; BTB unchanged at 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E.

Nineteen source-bound safety methods pass, including four 6000-cycle differential configurations, five compiled decode faults, directed redirect cases and all inherited multiplier/return-stack/commit checks. Eight core/cache comparisons, six safety-auditor tests and 196 pinned external ISA runs with eight rejection controls pass. The early differential attempt exposed one-shot procedural force RHS evaluation; continuous-wire forces and mandatory actual-redirect coverage correct the testbench. Failed evidence remains separate from the corrected build/safety-complete receipt. Both short UART logs are byte-identical to the immediate parent at 3000565 / 3001255 cycles with fcaf / c64e CRCs; no new long score is claimed.

Ordinary PDS 20260911-061640-1c2a196a is terminal at 9068 LUT / 4362 FF / WNS -0.260 ns at configured 151.2 MHz. The worst path moves to EX instruction bit 17 through source selection and ALU addition into MEM result bit 31, nine levels with 2.202 ns logic and 4.306 ns route. This fails timing; ordinary resources are not the complete-system denominator.

Full-ILA run decode-payload1-seed1 is now terminal at 9566 total LUT / 5048 FF / WNS -0.041 ns, two failing setup endpoints and TNS -0.057 ns. Fresh native discovery, actual Inserter and all 21 full-ILA auditor tests preserve 42 data / 33 trigger / 1024 samples with exact source/firmware bindings, but timing fails and the candidate is rejected. Bitstream SHA256 DC63DC0FBE7F62A7D4CE99421F24A675BAA556F8BFA25887841066801999536D. The worst complete-system path is register_valid[2] through ID masking/comparison into raw_pair_relation[0], ten levels with 2.052 ns logic and 3.984 ns route; the second violation ends at MEM result bit 22. The locally qualified three-metric result and board baseline are unchanged; no long score, remote-board or GitHub operation occurs.

## Guarded raw multiplier prefetch fails complete-system timing

New full_mul_prefetch_valid1 starts from full_return_stack1, not the rejected payload-factoring candidate. It moves register-valid checks out of speculative multiplier data inputs and into the precomputed marker eligibility, keeping WB forwarding and all ordinary masked EX operands. x0 and uninitialized-register cases fall back safely; initialized zero values remain eligible. CPU SHA256 0F9EFD4A6C17C6C7A6933AD0615CEC1089CEB79B916C6029AC1E253C10363001; unchanged BTB 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. Four exact substitutions retain the complete qualified-parent ancestry.

The source-bound fifteen-method safety suite passes 16384 operand/gate combinations, four actual-core fallback configurations, eight delayed/dependent multiply configurations, existing predictor/commit tests and compiled negative controls. Six safety-audit tests and eight independent core/cache trace/final-memory comparisons pass. Both short CoreMark results remain 3000565 / 3001255 cycles with fcaf / c64e CRCs. No long-run score is inferred.

Ordinary PDS 20260911-055209-ba24d059 is terminal: 9069 LUT / 4325 FF / WNS -0.010 ns at configured 151.2 MHz. The separate complete-ILA mul-prefetch1-seed1 job is also terminal: 9522 total LUT / 5055 FF / WNS -0.140 ns, eight failing endpoints and TNS -0.371 ns. Actual 42-data / 33-trigger / 1024-depth mapping and twenty-one audit tests pass, but timing does not. Bitstream SHA256: 1236DC2A621F44E3EAF72DF274A00EE3B725CB7E8717EBA1905AF8DAA7793880. No score promotion follows.

The new worst path is mem_result[19] -> branch/control logic -> id_instruction[23].CE: ten levels, 1.802 ns logic and 4.478 ns routing. Another failing path reaches raw_pair_relation[0] from id_instruction[16]. Decode payload capture lifetime is the next structural investigation, not a blind seed retry.

The current core independently passes 196 external RV32UI/RV32UM executions, eight expected rejection controls, the source/raw-log/coverage audit and four audit tests. Invocation SHA256: 38CD48643324FFE22B4B7C965E2122B7570360EB07C038612DC6F04F8614263E. See full_mul_prefetch_valid1/README.md and its source-bound safety/core/ISA receipts. Topic PDF pages 10-11 were rechecked; the five non-AI tasks, application, three metrics, ten-second minimum and ILA pipeline-analysis deliverables remain unchanged. No baseline replacement, browser or GitHub action occurs.

## Return-stack payload factoring passes functional tests but fails complete-system timing

New full_return_payload1 applies the previously tested three-substitution prediction-payload capture transformation to the timing-failed one-entry parent. It specifically targets the measured wb_data-to-fetch_prediction.CE path; the earlier payload-only failure is preserved as a different context. CPU SHA256 6A889FFD1E4E435A8AC44A0635F87B79CC331135C8DFC668CA9C1F2CF4CF6843; unchanged predictor 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E.

Fourteen source-bound safety test methods pass, covering four 6000-cycle dual-core configurations, four 35-case redirect configurations, five stack depths, 32768 commit/hint cases and compiled negative controls. Eight core/cache executions independently match trace/final-memory references. Both short CoreMark UART logs match the one-entry parent exactly: 3000565 / 3001255 cycles, CRC fcaf / c64e. This capture-only change claims no extra cycle savings.

Ordinary PDS 20260911-052657-0130a856 is terminal: 9115 LUT / 4331 FF / WNS -0.035 ns, one failing setup endpoint. Full-ILA return-payload1-seed1 is also terminal: 9550 LUT / 5045 FF / WNS -0.375 ns, 108 failing slow-setup endpoints and TNS -13.662 ns. Native discovery and actual 42-data / 33-trigger / 1024-depth mapping pass, as do twenty-two source/mapping/evidence audit tests. The candidate is rejected, not promoted. Bitstream SHA256: C74639C5FCC7C1D18A035D7680CC5347EE23C8D172DD601EBAF27B8119E6F4A1.

The limiting full-system path is register_valid[22] -> id_register_b_valid_1 -> id_operand_b[19] -> multiply_divide.unit/N98/gopapm/Y[3]: four logic levels, 1.033 ns logic and 4.286 ns routing, including a 1.845 ns final route to the APM. The mapped validity node has fanout 24 despite a synthesis hint of 16. This identifies a physical cone to review against earlier register-valid and multiplier-prefetch experiments; it does not justify an untested attribute change or blind seed sweep. No long-run simulation or resource-efficiency score is assigned to this failed version.

The changed core independently passes 196 external RV32UI/RV32UM executions and eight rejection controls, plus its complete artifact/coverage audit and four audit tests. Invocation SHA256: B8911CBB00C9E090CB36CD3A6D2E10FA2B90C3C486B7DA4ACFADD231927CED86. Six safety-audit rejection tests pass. See full_return_payload1/README.md and its source-bound receipts. No accepted-baseline replacement, remote-board or GitHub action occurs.

## One-entry return stack rejected after full-system timing; ISA passes

Ordinary run 20260911-050617-3125c6c4 completes with 9156 LUT / 4326 FF and WNS +0.090 ns at 151.2 MHz. However, the full-ILA return-stack1-seed1 run completes with 9429 LUT / 5026 FF and WNS -0.161 ns, 32 failing setup endpoints and TNS -2.286 ns. This candidate is not promoted. Full bitstream SHA256: 910693592F3B6F3B91E564C31362FA9957EA2B0471A5E5B51FE57279D8DE6CA8. The actual limiting path is wb_data[19] through the early forwarded branch comparison and frontend control to fetch_prediction[4].CE: ten logic levels, 2.216 ns logic and 4.042 ns routing. The ordinary LUT denominator must not replace the complete-system denominator.

Native Inserter mapping verifies all 42 data / 33 trigger channels and depth 1024. Unlike the two-entry parent, MEM-valid is the native parent alias board/soc/unused_pipeline_valid[3]; IF/ID/EX are core-local. The exact CPU output-port connection and register drivers are checked. Twenty-one source/firmware/mapping audit tests pass. Neither aliases nor channels are guessed from the preceding candidate.

The current core/predictor independently pass 196 pinned external RV32UI/RV32UM runs and eight expected rejection controls, plus the source/raw-output/coverage audit and four audit tests. Invocation SHA256: CE68CC248900D074D385384E76482CDB8AAD6D689BF682555F51DB313E528FE2. RV32UI contributes 164 executions, RV32UM 32; production cache geometry remains covered separately by core/cache tests. The ma_data test is an expected precise-trap rejection, not transparent misaligned-access support. This is not complete ISA certification.

No long-run score is launched for this timing-failed version. A distinct follow-up may reuse the already tested prediction-payload capture transformation against the now-measured fetch_prediction.CE path; previous failure of that transformation in a different core context is retained, not relabeled. The latest locally paired benchmark remains full_redirect_clock151200; the board baseline remains DC90363D. SCBV and electrical closure remain open.

## Cache factoring rejected; one-entry return stack reaches physical implementation

The cache-collision candidate's ordinary implementation passes 151.2 MHz with 9217 LUT / 4352 FF / WNS +0.022 ns, but its complete ILA placement fails at 9546 LUT / 5055 FF / WNS -0.132 ns. All 42 data / 33 trigger / 1024-depth native mappings pass, along with nineteen source/mapping/evidence audit tests. Full bitstream SHA256: 264A4558C1D23DC145BB2A24E13527956E199516EBE335B79E157D147F36A6C7. The limiting path is mem_next_pc[2] -> multiply_divide.unit/remainder[6].CE, with ten logic levels, 1.576 ns logic and 4.610 ns routing. No new accepted score or seed sweep follows.

That exact cache/CPU version independently passes 196 external RV32UI/RV32UM executions and eight expected rejection controls, plus its artifact/raw-log/coverage audit and four audit tests. Invocation SHA256: 97B2DD9E2964E68E4B4276E5BD4278ED9315A1F27FB139B57CB51B0399C4A57F. The external cache geometries and misaligned-trap exclusion remain explicit; this is not complete ISA certification. Source-bound synthesis comparison also confirms that unchanged core/predictor RTL can map to different cell counts after a cache change, so nested synthesis counts cannot replace complete post-route resources.

A separately source-bound committed-trace replay compares return-stack depths 1/2/4/8. Depth 1 retains 13443 correct targets and has 292 underflows; depth 2 has 13633 correct targets and 102 underflows. Both retain all committed targets at the two largest return-misprediction hotspots. Seven replay tests pass. This is only an architectural-order analysis, not a speculative predictor or cycle-savings claim.

New full_return_stack1 starts from full_raw_relation_payload and changes only .RETURN_STACK_DEPTH(2) to .RETURN_STACK_DEPTH(1). It does NOT carry forward the rejected cache change. CPU SHA256: C8D8002ADA85F260814640F94419FD1FAAF5450B4A38D2481B2EE560DA605D30; BTB remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. Four exact-delta tests, five predictor-depth runs of 4123 vectors, eight predictor fault rejections, 32768 commit/hint combinations, four commit/hint fault rejections and eight core/cache trace/final-memory comparisons pass. The initial inherited test found an omitted files ancestry field in the new receipt; the full qualified-parent reconstruction is restored, and original assertions pass in preserved .complete.log reruns.

Both short CoreMark runs pass with unchanged retired counts and expected CRCs: V0 3000565 cycles / fcaf; V1 3001255 / c64e. The one-entry cost is 150 / 50 cycles versus the two-entry raw parent, while remaining 3775 / 6585 cycles faster than the qualified no-RAS parent. These ten-iteration results are not qualified scores and do not prove either hard metric floor.

All twenty physical inputs are staged with the same clock, V0 6000-iteration firmware and complete peripheral configuration. Ordinary PDS run 20260911-050617-3125c6c4 starts at 151.2 MHz / seed 1, PDS PID 91328 (execution session 15868). Timing/resources are pending; preserve the live handle and do not restart on a polling timeout. Candidate-specific full-ILA mapping/implementation, paired long runs, application and external ISA evidence remain required. Both metric floors, all five non-AI tasks, GPIO/UART/full ILA, analysis and electrical acceptance remain active. No browser or GitHub action is performed.

## Cache collision factoring: current regressions pass; implementation started

The raw-relation candidate's alternate full-ILA placement is terminal and rejected: raw-relation-seed2 uses 9509 LUT / 5082 FF / WNS -0.092 ns, worse than seed 1 by 51 LUT and 0.026 ns. Its bitstream SHA256 is 4CE26B645684B753ADDE442ED1731278AE310C904260BFF10B17E4E306297A02. Its limiting path is mem_result[26] -> next_pc[21].CE, with 11 logic levels, 2.095 ns logic and 4.112 ns routing. No further blind seed sweep or accepted-baseline change follows.

New full_cache_collision_factored changes only cache collision-forwarding predicates relative to full_raw_relation_payload. It reuses the previously tested store-hit/refill state factoring, not the older failed whole design. This revisits the seed-1 data-cache read-index/forward_way1 critical path in the current CPU/validity/error-handling context. The older 135 MHz collision implementation failed overall timing, so success is not assumed. Current cache SHA256 is 0E5145F7F42F1F0DE0859C16A9C8A294A8ABD52BE975195A6EDC1834E0941D02; the immediate parent's CPU and BTB are unchanged and source-bound through candidate_sources.py.

The first cache test attempt exposes a coverage gap: mutations of incoming-index comparison and forwarded store data survive its large-geometry mutation scenario. Failed evidence is retained. An added small-geometry store-overlap case catches both without relaxing any assertion. The directed probe then passes and the complete rerun passes six test methods: 71 positive executions (32 writable configurations, six extra geometries, 16 bounds/error pairs and a directed store-overlap execution) plus ten compiled runtime rejection controls. The independent source/artifact/raw-log/Cartesian-coverage audit and five audit tests pass. Final cache manifest SHA256: 1B618E8C02F03AF406741DEB3EC6F2CA1134FF6C1C415E991B62F3B7464D347C.

Eight current core/cache runs pass instruction-trace and final-memory references, retaining the parent link-value and live operand-relation checks. Both ten-iteration CoreMark logs match the raw-relation parent byte-for-byte: V0 3000415 cycles / CRC fcaf; V1 3001205 cycles / CRC c64e. This timing-oriented cache change has no observed additional short-run execution-efficiency gain. It is not a qualified long-run score.

All twenty physical inputs are staged only after the current cache/core checks and paired UART equality pass. Ordinary PDS run 20260911-044832-e36e0300 later passes at 9217 LUT / +0.022 ns, but full-ILA cache-collision-seed1 fails at 9546 LUT / -0.132 ns; see the newer rejection entry. Preserve the live handle and existing artifacts; an observation timeout is not permission to restart. Complete native ILA mapping and full-ILA timing/resource validation remain required; no ordinary resource count may replace the full-system denominator.

GPIO, UART, 42 data / 33 trigger channels and 1024 samples remain mandatory. Both baseline metric floors, all five non-AI tasks, application and analysis obligations remain active. No new board score, remote access, electrical/SCBV closure or GitHub publication is claimed.

## Raw-relation payload: ordinary pass, full-ILA failure, independent ISA pass

The source A84C842258853FFB395533488909C0D41E6DACFCEBA4A88C384B6DAE6E8893CA completes ordinary PDS run 20260911-041355-3d1b7a0e: 151.2 MHz, 9058 post-route LUT, 4363 FF, setup WNS +0.020 ns. This is not the required full-system ILA resource count. A source-bound native-netlist comparison proves removal of all three raw_pair_relation enables while preserving reset initialization and clock/reset/output connections. Inclusive core and predictor synthesis counts do not change. Seven comparison/parser tests pass.

The actual full-ILA mapping passes with 42 data channels, 33 trigger channels and 1024 samples; all four pipeline-valid registers are native core-local nets with checked register Q drivers. Sixteen source, firmware, observer and mapping auditor tests pass. However, raw-relation-seed1 completes with 9458 total LUT / 5089 FF / WNS -0.066 ns, 11 slow-setup failing endpoints and TNS -0.200 ns. It is rejected, not a new score version. Bitstream SHA256 is E6A7AF8B248A33362F359E754F2D047BB2DAA8586F8119D8FC367C1C8F211E0C.

The limiting full-system path moves to data-cache request_address[5] -> tag/hit logic -> load-address bypass -> read-index comparison -> synchronous_writable.forward_way1, with eight logic levels, 2.090 ns logic and 4.210 ns routing. Thus the targeted enable removal is real, but does not prove timing closure. The subsequent raw-relation-seed2 placement is now terminal and fails at 9509 LUT / 5082 FF / WNS -0.092 ns; see the newer cache-collision entry for the decision and evidence.

This exact raw-relation core independently passes the pinned external RV32UI/RV32UM suites: 196 positive runs across four configurations plus eight expected rejection controls. The independent artifact/raw-log/coverage audit and four mutation/coverage tests pass. Cache set bits 1/4 in the external suites do not replace separate production-geometry cache tests; ma_data expects a precise trap and is excluded from transparent-misaligned support. Invocation SHA256: B33255B0085E9DA1734605910A1D74C7C4A33B393D8738D91CB751E715FB6C14. See experiments/full_raw_relation_payload/build/external-isa/audit.json and README.md for scope.

No paired long score, resource-efficiency qualification or accepted-baseline replacement follows from these screens. All five non-AI tasks, full GPIO/UART/ILA, application and analysis obligations remain active; electrical/SCBV acceptance remains open. No browser or GitHub operation is performed.

## Link reuse: external ISA passed; raw-relation enable optimization started

The link-reuse ordinary build passes 151.2 MHz at 9127 LUT / 4354 FF / WNS +0.018 ns, but both full-ILA placements fail timing. return-link-seed1 uses 9452 full-system LUT / 5092 FF / WNS -0.109 ns; return-link-seed2 uses 9558 LUT / 5088 FF / WNS -0.041 ns. Both retain verified 42-data / 33-trigger / 1024-depth mapping. Seed 2's 0.068 ns slack improvement costs 106 LUT and does not qualify the design. No long-run score or baseline replacement follows. Bitstream hashes are recorded in full_return_stack_link/README.md and each physical-qualification.json.

The exact link-reuse core passes the pinned 41-test RV32UI suite in four configurations (164 runs) and eight-test RV32UM suite in four configurations (32 runs), plus four expected rejection controls per suite. A separate artifact/coverage audit passes and rejects duplicate configuration coverage or false rejection success in four tests. ma_data is explicitly expected to trap; no complete ISA certification is claimed. The external configurations cover cache set bits 1/4, not the production geometry by themselves; production geometry remains covered by the separate cached-core tests.

The actual seed-1 full-ILA critical path ends at raw_pair_relation[0].CE after early comparison and ID issue control (ten logic levels, 2.060 ns logic, 4.205 ns routing). New isolated full_raw_relation_payload changes only the relation refresh guard relative to link reuse. It permits extra updates in invalid EX slots while preserving reset, later ID capture priority, EX operand-register updates and all system features. It retains parallel comparisons rather than introducing the previously rejected late input mux.

Its source-extracted sequential test passes 10000 cycles with 6649 live comparisons, 3373 held-EX observations, 848 invalid-slot differences and 160 flushes, plus reset/four-state data, and rejects three compiled faults. Existing predictor/commit tests and eight core/cache regressions pass. Both short CoreMark UART logs are byte-identical to link reuse (3000415 / 3001205 cycles). A missing predictor-bench setup file was restored before the successful complete regression; the initial failed log is retained. No performance gain is inferred from this source rewrite alone.

CPU SHA256 is A84C842258853FFB395533488909C0D41E6DACFCEBA4A88C384B6DAE6E8893CA; BTB SHA256 remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. Its ordinary PDS run 20260911-041355-3d1b7a0e starts at 151.2 MHz / seed 1 as PID 79896 after previous native work terminates. Ordinary and full-ILA physical results, candidate-specific external ISA, paired long scores, application and outstanding board/electrical acceptance remain pending. GPIO, UART, full ILA and both original numerical floors remain mandatory. No browser or GitHub operation occurs.

## Link-value reuse: synthesized area reduction

The source-bound compare_synthesis.py audit verifies identical long firmware, wrapper settings and twenty-input inventory shape, with only the intended CPU/predictor edits between the two return-stack implementations. Predictor hierarchy LUT decreases 815 -> 786 and LUT-carry count 35 -> 8, while predictor FF remains 322. Inclusive core hierarchy LUT decreases 3989 -> 3950 and LUT-carry count 1198 -> 1165, with FF unchanged at 1749. These nested hierarchy totals must not be added, and they are not post-route full-system resource measurements.

All three hierarchy-parser tests pass. Raw report hashes and the compared source/firmware bindings are recorded in full_return_stack_link/build/synthesis-comparison.json. This confirms a synthesis-area benefit from the reuse variant while preserving its measured short execution results. Native PDS PID 60528 remains in implementation when checked; final timing, post-route LUT count and full-ILA qualification are still pending. This supersedes the earlier statement that actual arithmetic removal remains unmeasured, but does not qualify a new system score.

## Return-stack full-ILA rejection and link-value reuse

The full_return_stack2 ordinary run completes with 9211 LUT / 4366 FF / WNS -0.324 ns. Its return-stack2-seed1 full-ILA build completes with 9669 full-system LUT / 5076 FF / WNS -0.205 ns at 151.2 MHz. The actual 42-data / 33-trigger / 1024-depth mapping and all twelve binding/native-channel tests pass, but timing fails, so the candidate is not promoted. Bitstream SHA256: 584DCEC0EAFF5EB6FFA13C52019731C0325F6E395480DFD1088A645043D1C7E5. Its worst full-ILA path is wb_rd[0] through forwarding and ALU logic to mem_result[6] (eight levels, 1.901 ns logic and 4.467 ns routing), different from the ordinary branch/control/comparison path.

The predictor synthesis hierarchy grows from 757 to 815 LUT, 256 to 322 FF, and 6 to 35 LUT-carry elements. These are synthesis counts, not full-system post-route resources. A new isolated full_return_stack_link variant eliminates the predictor's explicit update_pc+4 expression by reusing the core's existing committed JAL/JALR link value, mem_result. Two stack entries, update qualification, architectural recovery and all other physical inputs remain intact. This targets duplicated arithmetic; it does not claim to fix the observed worst timing path.

The new variant repeats the five-depth predictor checks with eight fault rejections, 32768 source-extracted commit/hint checks with four faults, and eight core/cache runs with independent trace/final-memory checks. Source-bound observers verify mem_result == mem_pc+4 on three committed pushes in each run. Both complete short CoreMark UART logs match the original return-stack candidate byte-for-byte: V0 3000415 and V1 3001205 cycles. The prior short-run gains are preserved, but no long-run score is inferred.

Current CPU SHA256: 452A354CD13DEA3342386942A3A97F69B48587A7B5DC1CEE4F59B1210D8ACDB8. BTB SHA256: 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. Ordinary PDS run 20260911-035000-1d9fd437 starts at 151.2 MHz / seed 1 as PID 60528 after the preceding native process terminates. Final timing/resources, actual removal of arithmetic, native complete-ILA validation, paired long runs and application qualification remain pending. The qualified local version and DC90363D baseline are unchanged; no browser or GitHub operation occurs.

## Two-entry return stack: execution screens pass, implementation pending

The payload experiment is rejected below. A new isolated full_return_stack2 candidate starts from the qualified full_redirect_clock151200 source, retaining GPIO, UART, caches and clock settings. A retirement-gated two-entry return-address stack supplements tagged BTB return entries. Stack updates use mem_fire && !mem_fault && mem_branch, not the existing level-sensitive BTB update signal, preventing duplicate updates while MEM stalls. Reset/invalidation, bounded overflow, underflow fallback and coroutine pop-then-push are implemented. Exact two-file edits are recorded in change-receipt.json.

The source-bound committed replay identifies 13735 returns and 1620 per-PC target changes; its two-entry stack supplies 13633 correct targets with 102 underflows. This is not actual fetch prediction or a cycle-saving estimate. The real RTL short screens improve V0 from 3004340 to 3000415 cycles (3925 saved, throughput +0.1308152%) and V1 from 3007840 to 3001205 (6635 saved, +0.2210779%), preserving CRCs and retired counts. Neither ten-iteration result is a reportable long-run CoreMark score.

All five tested stack depths, including disabled-stack equivalence, pass 4123 vectors each; eight compiled predictor faults are rejected. Source-extracted commit/hint logic passes 32768 combinations and rejects four faults. Six core and two cached-core runs pass independent ISA trace/final-memory comparisons using the qualified parent's matching tests. Current evidence is in full_return_stack2/build/*depthslice* and build/commit-gate-tests.log. Initial runner-format/old-bench failures remain retained, and no coverage requirement is weakened.

Initial ordinary PDS run 20260911-033350-a0abf706 exposes an unsupported sized cast and terminates during parsing. The equivalent explicit parameter bit slice is re-tested before starting the new isolated ordinary run 20260911-033657-f616c653 at 151.2 MHz / seed 1, PID 91708. Current CPU SHA256 is E1F37D3DAA7852B00A8E6AA916500046A6E005E6C6E96F3DA1400B53BE83D343; BTB SHA256 is DC54C0978A9BBE40905CB97081092D1B30313AB7F94B892036358B02E209AD57. Native synthesis is confirmed live; final timing/resources remain pending. A source-bound full-ILA implementation, paired long runs and application qualification still must follow before any promotion. No ordinary-LUT result may replace the full-system denominator.

The qualified local version and accepted DC90363D board baseline are unchanged. Full 42-data / 33-trigger / 1024-depth ILA and the original CoreMark/resource-efficiency floors remain mandatory. Board/electrical acceptance and the five non-AI tasks remain in scope; no browser access or GitHub upload occurs.

## Fetch-prediction payload: terminal full-ILA rejection

The completed payload-seed1 physical qualification reports 9602 full-system LUT, 5000 FF and setup WNS -0.042 ns at 151.2 MHz. Native PDS exits successfully, but timing and resource-efficiency qualification are false; a generated bitstream is not acceptance. Actual Inserter mapping retains 42 data / 33 trigger channels and depth 1024. The bitstream SHA256 is 4B10FD0E9444A08DA2410EFB9FEF196ED671E02036F7FE6D85CA5DF394549F80.

The actual worst full-ILA path now starts at wb_rd[1], passes through forwarding selection and the ALU carry-select addition, and ends at mem_result[25], with 11 logic levels, 2.287 ns logic and 4.010 ns routing. It is no longer the baseline fetch_prediction clock-enable path. Removing one late enable did not establish a net system benefit: LUT use grows by 232 versus the qualified local version, while both short-run cycle counts stay identical. Do not run long qualification or promote this candidate without a new justified change. The qualified local full_redirect_clock151200 version and DC90363D board baseline remain unchanged.

The following launch entry is historical and superseded by this terminal result.

### Historical full-ILA launch

The payload-only ordinary run 20260911-030148-7fb9c108 completes with 9153 LUT / 4282 FF and setup WNS -0.320 ns at 151.2 MHz, so it is not timing-qualified. After that native process exits, full_fetch_prediction_payload/build/ila/payload-seed1 starts as PID 40928. Actual Inserter output verifies 42 data channels, 33 trigger channels and 1024-sample depth, including the source-proven parent ID-valid alias. All twelve physical-source, complete-UART, firmware, native-channel and alias checks pass in build/full-ila-tests.log.

The complete full-system timing/resource result is still pending. The unchanged short-run UART and randomized/directed fetch tests establish bounded functional evidence, not a new clock, resource-efficiency or long-duration score. The qualified local version and accepted board baseline remain unchanged; no remote-board or GitHub operation occurs.

## Four-bit physical rejection and fetch-prediction payload experiment

The full_btb_history4 full-ILA stage history4-seed1 completes with 9606 total LUT / 5021 FF and WNS -0.438 ns at 151.2 MHz. Its 42/33/1024 mapping remains verified, but timing fails and it is not promoted. The failed image SHA256 is 0B89E5709F650C04D3E05291071F3A676E89D6D45B7AE6E0B8B7E8B5023A8FD1. The ordinary report's worst path ends at fetch_prediction[18].CE, through early-branch comparison/flush control, while the full-ILA worst path ends at raw_pair_relation[0].CE; these are not the same bottleneck.

A new isolated full_fetch_prediction_payload candidate starts from the qualified three-bit-history version and changes only CPU payload capture. Fetch control, discard, barriers, pending flags and next-PC selection stay unchanged. Prediction data can capture while idle, on normal response acceptance, or on acceptance of an unsent redirect-primed request, without the original late flush/barrier qualification on that payload register. The exact three substitutions produce CPU SHA256 10E46E6286F17F8DC25C619298EB5AA0F032939299CB7562A7EB818B5CE28A81 and are recorded in change-receipt.json. No architectural or debug feature is removed.

Four predictor/overlap combinations each pass 6000 randomized reference-versus-candidate cycles, including held responses, repeated external flush/barrier controls and overlapping transactions. Extra internal payload writes occur, but bus behavior and live instruction metadata remain equal. Four compiled capture faults are rejected. All four modes also pass 35 directed redirect cases with 444 checks per mode. Both complete ten-iteration CoreMark UART logs are byte-identical to the qualified parent, including cycles 3004340 / 3007840, CRCs, retired counts and profiling counters. This is a timing/resource-oriented experiment, not a new execution-efficiency score or a formal equivalence claim.

After confirming no other native implementation remains live, ordinary PDS starts as PID 94344, run full_fetch_prediction_payload/build/physical-project-complete/build/pds/20260911-030148-7fb9c108, at 151200000 Hz and seed 1. Seven physical-source checks pass. Native net discovery identifies an ID-valid parent alias for this new netlist; the full-ILA adapter verifies its exact bit connection and register driver rather than dropping or substituting a channel. The full-ILA runner waits for the verified ordinary process before starting. Final ordinary/full-ILA timing and resources remain pending at this entry. GPIO, UART and all 42 data / 33 trigger / 1024-depth ILA functions remain required. No qualified baseline, board access or GitHub state changes.

## Four-bit history: complete ILA implementation started

The full_btb_history4 ordinary run 20260911-024019-50a14ee9 finishes with 9121 LUT / 4291 FF and WNS -0.145 ns at 151.2 MHz, so it is not a timing-qualified image. After its verified PDS process exits, the full-ILA stage full_btb_history4/build/ila/history4-seed1 starts as PID 51172. The actual native Inserter output confirms all 42 data / 33 trigger channels and 1024-sample depth using this ADF's core-local pipeline-valid names, with exact register-Q driver checks. All thirteen candidate-specific source/configuration/firmware/native-map tests pass in build/full-ila-tests.log, including the four stage-dependent checks that were pending in the previous entry.

The full implementation is still running and must be observed by its actual process and final reports; no complete-system LUT count, passing timing result, long-run score or resource-efficiency claim is available yet. The short execution results remain 2998199 / 3004096 cycles for V0/V1. Neither the qualified local version nor the accepted board baseline is replaced. The next decision is based on this exact full-ILA physical result before launching paired long-duration qualification. Browser/board access remains gated and no GitHub upload occurs.

## Parallel two-way rejection and four-bit local-history follow-up

The parallel-read two-way predictor completes ordinary PDS 20260911-022751-c70713a8 with 9596 LUT / 4433 FF and WNS -0.523 ns at 151.2 MHz. Its complete ILA run full_btb_two_way_parallel/build/ila/parallel-seed1 also completes, with 10093 full-system LUT / 5114 FF and WNS -0.482 ns. Compared with the serial-read two-way ILA run, setup slack improves by 0.049 ns but total LUTs increase by 424, with no additional execution-cycle benefit. Both remain timing failures. The parallel failed bitstream hash is 6F1572E26DF58FF96D8F90F6F7B9B3E4C7E7984F0AF449F372765C7E1A29790F; physical_timing_passed, resource_efficiency_qualified, full_score_qualified and hardware_validated remain false. Eleven candidate-specific source, firmware, alias and native channel-map tests pass, retaining the actual 42/33/1024 ILA configuration without treating that as timing acceptance.

The new direct-mapped full_btb_history4 changes only the qualified predictor's HISTORY_BITS default from 3 to 4, retaining two-bit counters, 256 entries and all other full-system RTL. Its V0/V1 ten-iteration screens take 2998199 / 3004096 cycles versus 3004340 / 3007840, saving 6141 / 3744 with correct CRCs and unchanged retired counts. A same-counter-storage control, full_btb_history4_counter1, uses four history bits and one-bit counters but worsens both runs to 3064639 / 3066105 cycles (60299 / 58265 more); it is not selected for physical implementation. Neither short screen is a long-duration score or a resource-efficiency measurement.

Each history variant passes 96 independent parameter configurations, 18 compiled fault controls, two observationally equivalent unconditional-history cases and twelve compatibility comparisons across four test methods. The added directed sequence exercises the fourth history bit; masking that bit is rejected. The two-bit candidate adds 256 declared history bits and 4096 declared counter bits; the one-bit control preserves total counter bits but still adds history state. These declaration counts are not LUT/FF measurements.

After the verified parallel full-ILA process terminates, native ordinary PDS for full_btb_history4 starts as PID 86160, run build/physical-project-complete/build/pds/20260911-024019-50a14ee9. It uses V0 6000-iteration firmware, 151200000 Hz and seed 1; predictor source SHA256 is 64DD4C90AA68B1034A240D350A730347AB907931726A4232934EBBE7D10FCA0F. The immutable staging records actual HistoryBits=4 and CounterBits=2; nine physical-source/configuration negative-control tests pass, including rejection of inherited three-bit metadata. Native Inserter discovery identifies core-local pipeline_valid[0..3] for this ADF, unlike the previous two-way MEM-valid alias. A separate full-ILA runner is prepared with those discovered names and waits for this verified ordinary PDS process to finish before launching. Final ordinary and full-ILA timing/resources are still pending at this entry.

GPIO, UART and full 42-data / 33-trigger / 1024-depth ILA requirements remain intact. The qualified full_redirect_clock151200 version and accepted DC90363D board baseline are not replaced. Paired long runs, application and electrical qualification remain prerequisites for promoting a new candidate. No browser or GitHub operation is performed.

## Two-way physical result and parallel-read timing optimization

The serial-read two-way candidate completes ordinary PDS 20260911-020416-a810df1b with 9231 LUT / 4437 FF and setup WNS -0.705 ns at 151.2 MHz. Its complete ILA implementation build/ila/two-way-seed1-native-alias also completes, retaining all 42 data / 33 trigger channels and 1024 samples, but fails timing at WNS -0.531 ns with 9669 full-system LUT / 5127 FF. The failed full-ILA bitstream hash is 5EA206BE0E07536F90A40B34D7D970B28E95EC82E17674780D84AFCDDBCBA91A. Neither image is promoted; a generated bitstream and native exit zero are not timing acceptance. No long-run score or resource-efficiency qualification is claimed for this candidate.

The first ILA mapping attempt is retained at full_btb_two_way/build/ila/two-way-seed1: native Inserter drops the unavailable core-local MEM-valid alias, and the strict 42-channel audit rejects it before PDS starts. Native ins_list_nets identifies board/soc/unused_pipeline_valid[3]. The corrected mapping preserves that alias and proves its exact connection to the CPU pipeline_valid[3] port and the mem_valid register Q driver. Eleven tests pass, including missing actual native data channels, wrong alias bits, changed captured RTL, missing UART inventory, and firmware substitution. The malformed-path diagnostic probe is also retained; its own idle process is stopped only after its input-file error and command line are verified, then a forward-slash Tcl path succeeds.

The ordinary timing report identifies the optimization target: next_pc[4] -> folded index -> tag read/comparison -> fetch_hit_second (fanout 105) -> counter read/direction selection -> next_pc[16], with seven logic levels and 1.986 ns logic / 5.011 ns routing delay. A new isolated full_btb_two_way_parallel reads each way's direction state and target independently before selecting its output, removing the late way-hit bit from the memory read address. It changes only predictor RTL, with GPIO, UART and the complete debug requirement unchanged.

The parallel-read design passes 72 independent reference-model parameter configurations, 28 compiled negative controls and two observationally equivalent cases. Both complete ten-iteration screens match the serial two-way cycles exactly: V0 3001251 and V1 2999526, saving 3089 / 8314 against the qualified direct-mapped parent. CRC and retired counts remain correct. These are short execution results, not long-duration scores or measured timing improvements.

After the verified serial full-ILA PDS process exits, native ordinary PDS for full_btb_two_way_parallel starts as PID 90716, run build/physical-project-complete/build/pds/20260911-022751-c70713a8, using the captured full system, V0 6000-iteration firmware, 151200000 Hz and placement seed 1. Its final timing/resources and full-ILA follow-up remain pending and must be checked from the actual process and reports, without restarting a live implementation. The latest complete local metrics remain full_redirect_clock151200: 151.2 MHz, 3.337708280819477 CoreMark/MHz, 0.053859284104579 CoreMark/LUT and 504.6614920599049 CoreMark with 9370 full-system LUT. Electrical and board acceptance remain open. No browser or GitHub operation is performed.

## Same-capacity two-way BTB and raw asynchronous input audit

A shared-global-history storage screen passes its independent reference checks but worsens both complete short runs (3049626 / 3041204 versus 3004340 / 3007840 cycles). No FF/LUT saving is inferred from its smaller declared state, and it is not promoted.

The new experiments/full_btb_two_way preserves 256 entries, all local-history counter storage and the full SoC, adding two-way matching and per-set replacement state. The actual V0/V1 screens improve to 3001251 / 2999526 cycles, saving 3089 / 8314, with unchanged CRCs and retired counts. Seventy-two parameter configurations and 24 compiled mutation controls pass; three cold-conflict-replay tests also pass. The initial replacement-index width warning is fixed rather than suppressed; the failed compile remains recorded.

Native ordinary PDS is launched from the corrected immutable full-source staging as PID 71332, run full_btb_two_way/build/physical-project-complete/build/pds/20260911-020416-a810df1b, at 151200000 Hz with V0 6000-iteration firmware and seed 1. A prior missing-template staging failure is preserved and did not launch native PDS. This is not a qualified full-ILA implementation or a new metric result; full 42/33/1024 insertion, total-resource/timing qualification and paired long runs remain required.

Separately, audit_async_entries.py verifies the three qualified benchmark/application input netlists against their implementation hashes, then checks raw UART/KEY consumers across five modules and seven typed hierarchy links, together with the existing four synchronizer chains. All three pass. Eight tests reject added raw-input logic, aliases, initialized-wire bypasses, unknown nested expressions, wrong child types and synchronization bypasses, while accepting comments and lookalike names. This closes a bounded raw-input-fanout gap, not full CDC, routed-placement, MTBF, reset recovery/removal or board electrical signoff. Actual board configuration-power/SCBV evidence remains open.

The latest complete local metrics remain full_redirect_clock151200: 151.2 MHz, 3.337708280819477 CoreMark/MHz, 0.053859284104579 CoreMark/LUT and 504.6614920599049 CoreMark with 9370 full-system LUT. GPIO, UART and all ILA functionality are preserved. No remote-board access or GitHub upload is performed.

## Current-core event diagnosis and correlation screens

The completed source-bound control observer covers all 3004340 timed V0 cycles with 32 internal signal bits plus EX/MEM PCs. Both the complete UART result and the original retirement trace remain byte-identical. Its 255412 WB-empty cycles exactly conserve the earlier retirement-gap total; EX empty/fire/blocked counts also conserve the full interval. Actual events include 53021 early redirects, 3735 MEM flushes and zero interrupt-pending cycles. Eight control-analysis regression methods pass. See experiments/full_redirect_clock151200/CONTROL_EVENT_PROFILE.md and build/control-events-current/analysis.json within that experiment.

The diagnostic identifies high early-redirect counts in core_state_transition and late load-dependent branches separately. It does not label all bubbles as cache misses or claim additive removable stall costs. The source-bound observer changes only copied simulation output ports and its driver, not the qualified hardware RTL.

Two isolated predictor variants pass their independent model checks and complete paired CoreMark screens. Three-bit global/local XOR produces V0/V1 3030448/3030297 cycles, worse than 3004340/3007840. One-bit recent-global correlation produces 3004793/3008116 cycles, also worse. CRCs and retired counts match. Each predictor passes 72 parameter configurations and 24 compiled rejection controls. The one-bit test initially missed global-state mutations; directed interleaved-branch training/query sequences close that coverage gap before its SoC screens run.

Neither is selected for physical implementation: no execution gain or demonstrated timing/resource advantage supports promotion. This is not a claim that a short screen proves failure of the baseline throughput/resource floors. The completed full-system local candidate and its three metrics are unchanged: 151.2 MHz, 3.337708280819477 CoreMark/MHz, 0.053859284104579 CoreMark/LUT; throughput 504.6614920599049 CoreMark with 9370 total LUT. GPIO, UART and full 42/33/1024 ILA remain intact. The five non-AI tasks, continued optimization and electrical/board acceptance remain active; no GitHub upload or browser access occurs.

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

## Joint-score provenance tightened; full-ILA application implementation started

The candidate joint qualifier now reconstructs the expected simulator command from the captured configuration and requires the complete current RTL/driver/checker source set. It rejects mismatched configured/physical clocks, altered model clocks or compiler parameters, omitted CPU/driver/checker inputs and relabeling simulation as hardware, before reading score results. Eleven long-binding regression methods pass. Both actual in-progress candidate manifests pass these metadata-to-physical-configuration checks; this is not a claim that their long runs have completed.

Four exact-rational policy tests pass against the specified DC90363D baseline. A clock tradeoff with exactly equal score and resource efficiency is accepted, but a one-cycle score deficit or a one-LUT resource-efficiency deficit is rejected. Reduced LUT count cannot conceal a score below the baseline. These synthetic policy tests do not create measured scores or hardware qualifications.

Ordinary scope PDS `20260911-003942-efd1764f` completes with 9073 LUT / 4297 FF and WNS -0.020 ns, so that ordinary image is rejected. The subsequent full-ILA scope stage `20260911-redirect-clock151200-scope-seed1` has passed actual Inserter and source/firmware checks with 42 data / 33 trigger channels and depth 1024, and its native PDS implementation is running. The scope firmware remains bound to SHA256 72BE13E1AABEDFBEDF7EA2DE4A97DC49ECA020FDB2158DA64582ADF89C32655E. Neither the ordinary result nor Inserter success is substituted for a completed full-ILA timing result or application runtime pass.

## Current application host-budget and synchronizer evidence

The diagnostic application run `20260911-003422-a7552277` also reaches its explicit 600-second host limit. Unlike the first attempt, its preserved log proves steady simulated-clock progress through at least 2050000 cycles, one completed dump, the second capture dump in progress, and one EMPTY and TIMEOUT event. No terminal two-dump result is present. After confirming the process is terminal and its vvp child is gone, the next run `20260911-004616-9388dcd0` uses a recorded 1800-second host budget; RTL, firmware, stimulus timing and the 10000000-cycle testbench watchdog remain unchanged. This increases simulator wall-time allowance, not the simulated 30-second application timeout. Three logging regression methods pass again. Runtime qualification remains pending; the two shorter host-budget attempts are not reclassified as passes.

Both passing CoreMark full-ILA netlists now also pass the bounded native-cell synchronizer review. Each netlist hash is checked against its physical invocation first. Four direct two-stage UART/GPIO/reset chains have the expected cells, clock/reset connections and first-stage fanout. Six structural tests pass, including bypass, wrong-clock and extra-fanout mutations. Per-image `async-structure.json` receipts and `experiments/full_redirect_clock151200/LOCAL_ELECTRICAL_REVIEW.md` retain explicit false status for whole-design CDC/electrical signoff, placement review and metastability proof. Actual remote-board configuration-power/SCBV evidence remains missing; the browser gate stays closed.

## Paired physical images pass; application qualification remains open

Both `full_redirect_clock151200` CoreMark images now pass full-ILA physical qualification at configured 151200000 Hz, each with 9370 total LUT / 4986 FF and setup WNS +0.017 ns. Performance stage `20260910-redirect-clock151200-seed1` has bitstream SHA256 ED45D1C8D1678E0C70C671AEAC086415CA4D7EBFD66FBD8AD7A3EA4453D7B556; validation stage `20260911-redirect-clock151200-v1-seed1` has SHA256 1C93B95632E9B6DB6F01C72D0968840F37500718F7CFDAB8F8E6AFEC46F31B23. Both actual Inserter mappings preserve 42 data channels, 33 trigger channels and depth 1024. Their respective firmware, source snapshots, native reports and invocation/output hashes are checked independently. This is paired physical-image evidence only: the candidate-specific long runs are still pending, so execution/resource-efficiency qualification and baseline replacement remain unproven.

The application firmware has passed its six firmware-gate test methods; six long-result binding tests, two launcher-argument tests and three execution-log tests also pass. Runtime diagnostic `20260911-003422-a7552277` shows clock cycles advancing through the first capture dump and a successful simulated timeout event; it has not yet completed both captures. Ordinary scope PDS starts as `20260911-003942-efd1764f`, serialized after validation full-ILA completion. The intended scope full-ILA stage `20260911-redirect-clock151200-scope-seed1` waits for that exact ordinary PDS process to exit and checks memory headroom before starting. The initial host-timeout attempt is preserved separately. Remote-board access remains gated by incomplete application/electrical acceptance and pending long-run qualification.

## Application integration and validation-image launcher update

The initial scope simulation `20260911-002206-0ecbfd1a` terminates at the 600-second host limit without a terminal application result. Its incomplete manifest, compiled image and input snapshot remain intact. After verifying its vvp process is gone, a new diagnostic run `20260911-003422-a7552277` starts with unchanged RTL/firmware, streamed execution logging, unbuffered simulator stdio, periodic cycle/status observations and UART log flushing. Three logger tests verify success, failure and timeout diagnostics are retained. Live observations show EMPTY, the injected 64-bit TIMEOUT, the first capture and its dump progressing; this is not yet a complete two-channel application pass. The cause of the initial timeout is not established, and no RTL failure or successful application result is inferred from it.


For `experiments/full_redirect_clock151200`, the scope firmware is rebuilt at 151200000 Hz, with 1210-cycle sampling, a 4536000000-cycle (30-second configured-clock) timeout, and console delay zero. Its SHA256 is 72BE13E1AABEDFBEDF7EA2DE4A97DC49ECA020FDB2158DA64582ADF89C32655E. The first builder invocation stops before compilation because the isolated directory lacks the existing toolchain descriptor; copying the established descriptor and verifying the live RV32 compiler target/version resolves this without rebuilding the toolchain. The scope runner uses the current captured RTL and starts `build/scope-current/20260911-002206-0ecbfd1a`; no application pass is claimed until terminal assertions and raw-capture checks complete. UART stimulus uses 15750 cycles per bit, GPIO pulses 44800 cycles, and the timeout test injects counter jumps of 4294967296 and 241032704 cycles rather than waiting 30 physical seconds.

Twelve joint-score binding and application-firmware test methods pass. The joint local qualifier explicitly rejects the current incomplete long pair and cannot issue a score based on the already-passing performance image alone. The new application runtime verifier additionally checks current RTL, firmware, runner, decoder, executable, raw UART and terminal assertions.

Ordinary validation-firmware PDS `20260911-001344-ee795aac` completes with 9073 LUT / 4297 FF and WNS -0.020 ns, so that ordinary image fails timing. The first full-ILA launcher invocation stops before stage creation because a scalar PowerShell string is splatted as individual characters. The fix retains a typed string array; two native-argument tests reproduce the original defect and verify the actual runner sends either one complete `--validation` argument or no argument. Only after confirming the original invocation is terminal and no validation stage exists is the corrected `20260911-redirect-clock151200-v1-seed1` stage started. This is not a rerun of a still-active PDS process. Both candidates and prior baselines retain their existing qualification boundaries.

## Follow-up — September 11, 2026: full-ILA seed-1 timing pass and long-run evidence

The 151.2 MHz candidate now has a passing performance-image full-ILA implementation: `experiments/full_redirect_clock151200/build/ila/20260910-redirect-clock151200-seed1`, 9370 LUT / 4986 FF, setup WNS +0.017 ns, actual 42 data / 33 trigger channels and depth 1024. The bitstream SHA256 is ED45D1C8D1678E0C70C671AEAC086415CA4D7EBFD66FBD8AD7A3EA4453D7B556. Source, firmware, invocation, placement seed, actual Inserter mapping, native timing/resources and output hashes are checked by the physical qualifier. This is one passing physical image, not a complete paired score or board result; SCBV/electrical acceptance remains open. The failed ordinary and full-ILA seed-2 runs remain recorded.

Separately, the 154285714 Hz `full_redirect_accept` V0/V1 long simulations `20260910-231803-b547d994` / `20260910-231828-3483fd63` complete all 6000 iterations and pass source-bound paired auditing: 1797640625 / 1799846469 timed cycles, 1649428424 / 1649775523 retired instructions, final CRC a14c / 18e1, and modeled durations 11.651374 / 11.665672 seconds. The performance run projects 3.337708280819477 CoreMark/MHz and 514.9607052299455 CoreMark at its own configured clock. This candidate still fails its full-ILA timing at -0.532 ns; these results do not qualify that image, replace a baseline, or become scores for a different clock/core. See `experiments/full_redirect_accept/build/long-comparison.json`.

The 151.2 MHz candidate launches its own clock-specific long V0/V1 runs `20260911-001254-0e98e281` / `20260911-001315-6a0c1e04`, each with the established 6000000000-cycle limit. The separate validation-firmware ordinary PDS run is `20260911-001344-ee795aac`; full-ILA validation seed 1 is serialized after its verified PDS process exits and available commit headroom is checked. Long-run, paired physical-image, application and full electrical qualification remain open. Browser/remote hardware access remains gated.

## Follow-up — September 11, 2026: measured redirect benefit and timing rejection

The completed ordinary 151.2 MHz implementation `20260910-233603-e3b63565` uses 9072 LUT / 4290 FF and fails setup at -0.026 ns. The serialized full-ILA retry `20260910-redirect-clock151200-seed2-retry1` completes native PDS and bitstream generation but also fails setup: 9399 LUT / 4998 FF, WNS -0.159 ns, bitstream SHA256 C0F1C2B0B47E3B54AB358044E10BC7F6D853989CADB59FE296AFE3C1BBE1FC05. Actual 42-data / 33-trigger / 1024-sample ILA and input/output provenance checks pass; they do not override failed timing or unresolved SCBV/electrical requirements. The earlier allocation failure remains a separate failed attempt. A fresh full-ILA seed-1 run `20260910-redirect-clock151200-seed1` starts only after the seed-2 PDS process exits and the memory-headroom check passes.

The clock-specific retirement observer and independent paired comparison now pass. All 2748929 timed retired PCs and instructions match the unchanged `full_control_commit` reference. Redirect priming reduces the interval from 3060873 to 3004340 cycles: exactly 56533 adjacent-retirement intervals each save one cycle, 2692395 are unchanged, and none worsens. Savings group as 53708 following conditional branches, 1619 following JALR and 1206 following JAL. These groups are not direct misprediction/stall-cause measurements and are not new long-duration scores. Six comparison/provenance test methods pass, including rejection of altered traces, executable, firmware, runner and current CPU hashes. See `experiments/full_redirect_clock151200/EXECUTION_PROFILE.md` and its `build/execution-profile-current/paired-comparison.json`. The accepted hardware baseline and locally qualified `full_control_commit` version remain unchanged.

## Version update — September 10, 2026: redirect priming clock tradeoff

The isolated `experiments/full_redirect_clock151200` retains every one of the twenty physical RTL/PLL/constraint inputs of `full_redirect_prime` byte-for-byte. Only the clock configuration changes to 151200000 Hz; GPIO, UART and full 42-data / 33-trigger / 1024-sample ILA remain required. This tests a clock tradeoff after all three parent placement seeds failed at 154285714 Hz; lower frequency is not assumed to repair timing or satisfy either performance floor.

Clock-specific V0/V1 firmware and ten-iteration RTL runs `20260910-233631-e15b5716` / `20260910-233649-cc01ef34` pass with 3004340 / 3007840 timed cycles, matching the parent execution counts and CRCs. These are short screens, not new long-duration or hardware scores. The new ordinary PDS build is `20260910-233603-e3b63565`; physical qualification and source-bound paired long runs remain open. The accepted hardware baseline and locally qualified `full_control_commit` version remain unchanged.

Six clock/source/firmware tests and twenty physical-wrapper/ILA/evidence-gate tests pass. The PLL test elaborates the actual source at I=1, M=2, F=14, O=5 and rejects a wrong-ratio mutant; it is not an analog or independent oscillator measurement. The short comparison binds unchanged simulation RTL, command settings, retirement counts, CRCs and cache profiles, with only the documented firmware clock change.

The first full-ILA stage `20260910-redirect-clock151200-seed2` passes actual Inserter verification of all 42 data / 33 trigger channels and depth 1024, then exits with native PDS code 1 during placement: allocation of 1048512 bytes fails. No timing result or qualified bitstream is produced. The concurrent ordinary build remains authoritative and is not restarted; its exact process is awaited before a fresh `20260910-redirect-clock151200-seed2-retry1` attempt, with at least 3.5 GiB of available commit headroom checked first. Original input hashes and failure logs remain intact.

## Version update — September 10, 2026: pending-acceptance simplification

The isolated experiments/full_redirect_accept changes only the redirect prediction commit predicate relative to full_redirect_prime (CPU SHA256 FB691C04B9221F0DDEB7EF897F5C30D052128696051E62BEB4BD646C0F335B01). The pending-fetch invariant already implies an active, unsent, undiscarded request, so the explicit i_req_valid term is redundant. Reset establishes the invariant; request acceptance, barriers and repeated redirects clear pending state. The change targets implementation logic, not instruction count or an added pipeline stage.

- The actual RTL passes 288 one-step state/control combinations with each fetch-overlap setting, covering every binary state satisfying the pending invariant and all five selected binary controls. These checks isolate the fetch-control inputs and are not a whole-core formal proof.
- Twenty-four live RV32I core comparisons (predictor x fetch overlap x load-use bubble x three randomized bus seeds) compare every output against the unchanged reference core every cycle and also pass independent architectural trace checking. The existing four directed redirect modes and six rejected RTL mutations pass.
- Matched ten-iteration V0/V1 results remain exactly 3004340 / 3007840 cycles, with identical retired counts, CRCs and cache profiles versus full_redirect_prime. Builds are 20260910-230309-3456598d and 20260910-230321-0d85a2ff. This structural change claims no additional execution gain.
- Twenty-seven physical/evidence/ILA audit tests pass. The first Inserter stage rejects a missing ID-valid alias; the fresh stage proves that alias through the native register Q and CPU output port connection. Actual Inserter output verifies all 42 data / 33 trigger channels and depth 1024. GPIO/UART and the remaining physical sources are unchanged.
- Ordinary implementation 20260910-230437-872a1ac3 fails timing at WNS -0.275 ns with 9098 LUT / 4283 FF. Full-ILA implementation 20260910-redirect-accept-seed2-remapped also fails: 9481 LUT / 5020 FF, WNS -0.532 ns at 154285714 Hz, bitstream SHA256 B7B4ACE8B5CC8B9309443BE3ECB8FDBF837DEA694AC9E53DB0A3A02DC8E45292. The structural simplification is therefore not promoted; removing a Boolean term did not imply lower implemented resource use or better timing.
- New long V0/V1 runs are 20260910-231803-b547d994 and 20260910-231828-3483fd63, each using the established 6000000000-cycle limit. These are independent current-candidate simulations, not reclassified versions of the incomplete parent run. The long-result audit reconstructs both recorded CPU substitutions from the locally qualified reference and rejects incomplete or short output. Four long-duration guard tests pass; no long-run or hardware score is claimed before completion.

## Version update — September 10, 2026: redirect priming

Version changes are recorded in this file. The accepted hardware baseline remains DC90363D (501.0657302224314 CoreMark, 3.181369715697977 CoreMark/MHz, 9374 full-system LUT, 0.053452712846429634 CoreMark/LUT at configured 157.5 MHz). The latest locally qualified candidate remains full_control_commit; its values above are local projections, not board measurements.

The isolated experiments/full_redirect_prime changes only rtl/rv32_core.sv (SHA256 81671AD0A87EBD75F68D6351A85DAA21899CA42D27472B4C5B325F59EA8ABDEE). It primes an available fetch slot on redirect and captures predictor metadata when the request is accepted. GPIO/UART, memory, PLL and constraints are unchanged. Outstanding requests retain their address and drain; repeated redirects, errors, reset and FENCE.I barriers are covered by directed regressions.

- Matching-firmware ten-iteration V0/V1 RTL runs use 3004340 / 3007840 cycles versus 3060873 / 3065630 in full_control_commit: throughput improves 1.8817% / 1.9213%. Retired counts and CRCs match. Short runs are execution screens, not reportable scores.
- Four directed fetch-FSM modes pass 35 scenarios and 444 checks each; six runtime RTL mutants are rejected. Six randomized core/reference runs, two GPIO configurations (2976 checks and three interrupts each), fourteen precise M interrupt/cancel cases, external-UART SoC/fault tests, and pinned external ISA suites (164 RV32UI + 32 RV32UM runs with four rejection controls per suite) pass. These are not whole-core formal proof or ISA certification.
- Full-ILA seed-2 implementation at experiments/full_redirect_prime/build/ila/20260910-redirect-prime-seed2-remapped uses 9406 LUT / 5004 FF but fails setup timing at 154285714 Hz: WNS -0.450 ns. All 42 data / 33 trigger channels and 1024-sample depth are verified by actual Inserter output. The first obsolete-alias stage was rejected before routing and remains recorded.
- The worst routed path starts at data-cache request_address[4], crosses tag/hit selection, CPU forwarded address generation, and returns to the data-cache synchronous read-forward comparison. Its reported delay is mostly routing; no claim is made that reducing clock alone preserves the score/resource floors.
- Alternate full-ILA placements have completed and also fail: seed 1 uses 9416 LUT / 5004 FF at WNS -0.238 ns; seed 3 uses 9335 LUT / 4984 FF at WNS -0.613 ns. All three builds retain 42/33/1024 ILA functionality. The lower seed-3 LUT count is not an efficiency qualification because timing fails. Native PDS exits successfully, but the qualification script rejects each image.
- experiments/full_redirect_prime/build/placement-comparison.json verifies identical synthesized inputs, firmware, constraints and functional ILA configuration across seeds. Only the design path and Inserter timestamp comment are normalized for FIC comparison. Twenty-nine audit test methods pass, including seed/command mismatch rejection and rejection of ten-iteration results as long-run evidence.
- Current-clock scope application simulation now passes at experiments/full_redirect_prime/build/scope-current/20260910-224857-b5792441: 2705484 cycles, two waveform dumps, UART 0x55 and KEY trigger verification, zero late samples, EMPTY and timeout behavior. Captured RTL, firmware, executable and outputs are hash-verified. UART simulation clocks are accelerated and the 64-bit counter is advanced across 2^32 for the timeout test; this is not a physical 30-second run or application-image timing qualification.
- The first 6000-iteration V0 execution screen, 20260910-224408-85870a10, terminates at the incorrectly selected 2500000000-cycle limit during result printing, after reporting 11651 timing ticks. It has no final CRC/complete result and must not be scored; V1 was not started by the sequential wrapper. The established parent long runs used a 6000000000-cycle limit and took approximately 4.718 billion total cycles because firmware pacing is 2700000 cycles per output character. A subsequent long run must retain that established budget. This is a test-budget correction, not a demonstrated CPU/CRC failure; the failed logs remain intact.

This experiment is not promoted and has no new hardware score. No GPIO/UART/ILA feature is removed to improve the resource denominator. Remote-board access at Chrome 19476 remains gated on complete local qualification; electrical/configuration-power evidence remains open. No GitHub upload is performed.

## 最新补充：双版本独立计分

最终分别验收无MMIO外设版与含GPIO、UART等的完整外设版，三项指标均须绑定各自的源码、固件、位流及总LUT。含GPIO的CoreMark版本可正常成为跑分基线；独立GPIO诊断固件不运行CoreMark，仅用于功能验收。详细证据与未完成项见[PERIPHERAL_VARIANT_MEASUREMENT.md](PERIPHERAL_VARIANT_MEASUREMENT.md)。

## 最新范围更新：ILA仅本地PDS验证

2026-09-09用户已取消远程ILA验收要求。保留通过的42位采样/33位触发精简版；停止仅服务远程网页的Platform42分支，不启动其V1实现。当前CoreMark双种子实板计分已通过，GPIO与应用作为独立功能继续验证，不成为性能测评前置。结构/时序、RTL算法波形及实板成绩的来源边界统一见[LOCAL_ILA_ACCEPTANCE.md](LOCAL_ILA_ACCEPTANCE.md)。下文“远程ILA尚未完成”属于旧要求，不再列为当前阻塞项。



## 2026-09-09 当前实测状态（替代下文旧的进行中状态）

当前DC90363D源的V0、V1完整6000轮RTL均已通过，周期/退休分别为1885980108/1649428424、1888935654/1649775523，原始结果与冻结基线一致。两份独立插核20260909-131103-bd14dfaf、20260909-134154-631c0e9f均为157.5 MHz、总9374 LUT、4984 FF、WNS +0.078 ns。

2026-09-09通过用户指定Chrome端口19475，在实验箱5（平台device_id=15、PG2L200H）分别烧录上述两份镜像，115200 8N1，V0/V1各完成一次6000轮实板运行。两次全部CRC通过，周期/退休与对应RTL完全一致；计分501.065730222 CoreMark、3.181369715698 CoreMark/MHz、0.053452712846 CoreMark/总LUT。该分数按64位周期和配置频率计算，不采用固件整数秒显示的545 Iterations/Sec，也不声称独立测量了晶振频率。

原始UART、接收数据包十六进制、烧录成功响应、截图和来源审计保存在build/hardware/regfile-fanout-minimal-20260909-box5；审计入口build/audit_regfile_fanout_minimal_hardware.py。本次仅验证实板计分，不代表算法ILA、GPIO/应用、电气或长期稳定性全部完成。未重新启动程序直接再次发送G没有输出，不计作第二次通过；固件需要重启后才能重新运行。设备已释放，Chrome19475保持登录，没有Git操作。

**实板ILA尚未通过：** 当前原厂FIC为42位data、33位Basic trigger，平台实际只显示33通道。读取本次已加载前端代码确认其FIC解析忽略dataChannel/dataPortWidth，按triggerChannel生成通道表，并用同一ilaChannelCount配置采样和触发。为避免通道错位，未启动此配置的采集，不将已有RTL波形冒充实板波形。证据见同目录platform-ila-compatibility.json及ila-import-33-trigger-only.png。下一步建立独立的平台兼容精简profile，保持完整EX_PC及必要流水状态，先验证映射、平台协议、总资源及时序，再上板；不篡改本次已通过42/33镜像或FIC。

GPIO普通实现20260909-135747-4431b8c0已结束但WNS -0.157 ns，拒绝上板。当前源scope应用已修正157.5 MHz时间基准与64位30秒超时，并通过当前源实仿真；正式应用位流/KEY边沿仍待实测。SCBV电源依据及异步I/O审查未关闭，冻结基线未替换。



当前联合目标：按用户最新修订，保持已通过501.065730222 CoreMark基线的频率至少157.5 MHz、执行效率至少500000000/157165009 CoreMark/MHz，插核总资源效率严格大于0.05 CoreMark/LUT（等于也拒绝）；不再沿用此前0.052或冻结版0.052994789024的插核资源下限。先完成ILA/GPIO、两份固件的完整插核时序与远程实测，之后提高资源效率且不降低另外两项。冻结文档中的旧比较规则保留历史含义，不更改121件基线证据。当前规则及进度见RESOURCE_MARGIN_ILA_PLAN.md。原五项非AI、应用、稳定性与电气边界不能只用数值测试关闭。

## 新精简ILA进展（尚未完整验收）

DC90363D源的42位采样/33位Basic触发插核20260909-131103-bd14dfaf实际通过157.5 MHz、WNS +0.078 ns、9374总LUT、4984 FF；完整位流与独立物理审计已生成。当前源ISA/SoC与真实RTL三算法窗口验证通过，但本源配对6000轮、验证固件独立插核、真实板上ILA/GPIO以及电气验收仍未关闭。9374 LUT按冻结周期换算的0.053452712846429634仅为条件数值，不是新完整计分。SCBV与异步I/O报告警告保留；冻结基线不替换。详见REGFILE_VALID_FANOUT.md。

## 当前资格

WB字节预计算候选 `wb-byte-retime-stage` 的157.5 MHz性能/验证两套实现均通过：WNS +0.026 ns、9455 LUT、5247 FF。双6000轮 `20260909-043407-770c577b` / `20260909-044944-64801d83` 和完整来源/更新目标审计均通过：3.181369715697977 CoreMark/MHz、501.0657302224314 CoreMark、0.052994789024054086 CoreMark/LUT。已达到当前后备频点下的本地三指标门槛，尚非160 MHz或新实板结论。最终4项/15反例验收已通过，本地基线已冻结并重新核对121件证据；详情见 `docs/WB_BYTE_RETIME.md`。当前源码的双短测实际退休轨迹及24个运行反例也已通过，执行热点见 `docs/WB_BYTE_RETIME_PROFILE.md`，不与正式长测混用。

151.2 MHz、3.181370 CoreMark/MHz是旧目标下的本地历史合格结果，既不是当前500分结论，也不是最新源实板证据。下述时间点、候选与分数保留为历史记录，不能跨候选拼接频率、周期或LUT。

## 历史验收记录与未关闭边界

加载/普通地址改为16位并行加法后，146.25 MHz候选以8689 LUT、5124 FF、WNS +0.107 ns通过原始物理报告与独立恢复审计；比完整父版本少154 LUT、少5 FF、裕量增加37 ps，双短测周期不变。约1016万正向组合用例、196次ISA和集成回归通过；原包装后处理异常及旧夹具失败记录保留。本候选自己的配对6000轮与严格来源审计现已通过：3.128078805 CoreMark/MHz、457.481525238 CoreMark、0.052650653152 CoreMark/LUT，同频资源效率提高1.7724%；这是本地RTL/PDS结果，尚非最新源实板成绩。148.5 MHz现已完成两套实际PDS（8677 LUT、5117 FF、WNS +0.066 ns）和双短测；双6000轮及严格配对审计现已通过：3.128078805 CoreMark/MHz、464.519702549 CoreMark、0.053534597505 CoreMark/LUT（本地RTL/PDS，尚非新版实板），详见CLOCK148500_CARRY16.md。见 LOAD_ADDRESS_CARRY16.md；生产RTL不变，本轮不上传GitHub。

取指地址选择器的146.25 MHz隔离工程已完成配对PDS与双6000轮长测：8843 LUT、5129 FF、WNS +0.070 ns。本地RTL投影3.1280788050 CoreMark/MHz、457.4815252381 CoreMark、0.05173374706 CoreMark/LUT；相较144 MHz完整基线，执行效率不变、吞吐增加1.5625%、资源效率下降0.92976%，保留8626 LUT基线而非宣称三指标全胜。双CRC、计分时长和实际来源绑定审计通过，首次日志节流预算不足的失败保留；不是实板成绩。见 CLOCK146250_FETCH_ADDRESS_SELECT.md、FETCH_ADDRESS_SELECT.md；生产RTL不变，本轮不上传GitHub。

替换路选择复用采样有效位后，144 MHz候选降至8639 LUT、5126 FF，比上一失败版少844 LUT，但WNS -0.765 ns仍失败，不采用。11项缓存测试、52个变异拒绝、196次ISA、双短测、SoC及来源审计通过；周期未变，没有新CoreMark成绩。见CACHE_VALID_REUSE.md；下一步检查取指地址选择器的中断/背压依赖，生产RTL与GitHub不变。

I/D缓存共同提前采样有效位完成10项缓存测试、44个变异拒绝、196次ISA、双短测和SoC重放，但144 MHz PDS以9483 LUT、5147 FF、WNS -1.212 ns失败，较D-cache单独采样父工程多734 LUT，不采用、不启动新长测。审计与反例通过只证明失败证据一致。见CACHE_VALID_BOTH.md；生产RTL与GitHub不变。

按ready条件采样有效位的候选以8749 LUT、5154 FF、WNS +0.148 ns通过144 MHz；功能与来源回归通过，尚未替换8626 LUT完整基线，也没有本候选新长测或实板分数。后续146.25 MHz独立工程完成双短测，但PDS以8701 LUT、5160 FF、WNS -0.231 ns失败，不采用、不启动配对长测；详见CLOCK146250_VALID_ENABLE.md。见CACHE_VALID_ENABLE.md；实板、ILA、独立GPIO、电气约束、应用与稳定性仍未关闭。

I-cache填充碰撞隔离实验已完成196次ISA、同周期短测及两种GPIO/UART固件的成对重放；144 MHz实际WNS -0.050 ns，尽管少14 LUT仍不合格、不替换完整基线。见READONLY_FILL_COLLISION.md。最新物理构建为20260908-000502-b57d9d5b，不代表新实板或新长测成绩。

WB匹配预译码完成独立元数据状态检查、真实CPU逐拍不变量及同周期回归，但144 MHz实现为8658 LUT、5139 FF、WNS -0.046 ns，被时序门槛拒绝；不替换下述完整配对基线。详见WB_MATCH_PREDECODE.md。功能测试通过不关闭实板、ILA、电气约束或整体任务验收。

本轮重新对照原始topics/紫光同创.pdf第10、11页（印刷页8、9）：非AI任务确为基础3项与高阶2项；此外仍需三项性能指标、实际应用及CoreMark关键算法ILA分析。AI加速按用户要求暂缓，不能将其删除后顺带省略应用、实板或分析文档。

当前全偏移加载旁路候选已完成自身144 MHz性能/验证6000轮本地配对：1918110244/1921816141周期，双CRC和实际PDS绑定审计通过，8626 LUT、WNS +0.005 ns。本地RTL投影3.1280788050 CoreMark/MHz、450.4433479268 CoreMark、0.05221926129 CoreMark/LUT，满足用户0.031资源效率模型门槛；不是实板分数或物理极限证明。详见LOAD_USE_ADDRESS_BYPASS.md。

| 原始五项非AI任务 | 当前证据与未关闭边界 |
| --- | --- |
| 基础1：RV32I处理器 | 已实现并有CPU差分及固定外部ISA覆盖；新候选非完整ISA认证，不能以选定用例代替全指令/异常空间证明。 |
| 基础2：不少于三级流水线 | 五级流水线、前递/停顿/冲刷与随机总线延迟已有验证；新增选择器实验单独核验，未替换已完整配对核心。 |
| 基础3：基础外设 | UART/GPIO/定时器等已有仿真与历史实板自检；独立GPIO输入/按键、新源实板复测仍待完成。 |
| 高阶1：两路I/D Cache及突发效率 | 已实现并有数据/指令路径、替换、写回、错误及背压测试与历史硬件消融；当前源完整硬件边界验证仍不足。 |
| 高阶2：动态预测与异常/中断 | BTB与M-mode异常/中断实现已有差分、优先级及精确M中断覆盖；新源实板、最新ILA和长期稳定性未完成。 |

操作数选择器的priority/onehot实验保持双短测周期和196次ISA逐案结果，但priority增加112 LUT仅增加6 ps裕量，onehot时序失败；不作为联合优化升级，详见LOAD_OPERAND_SELECT.md。当前候选的SCBV/完整IO电气依据、新源ILA、真实应用复测、长期稳定性及最终逐项验收仍未关闭。本轮不上传GitHub。

以下按阶段保留历史记录；涉及“正在运行”或“本轮”的旧段落须以对应最新完整审计与上列状态为准。


零偏移加载地址旁路使两种十轮CoreMark分别少28200/29290周期（-0.864366%/-0.895620%），5263360次定向比较、真实指针固件及196次外部ISA通过，但单独版144 MHz时序差65 ps；按实际乘法关键路径组合进位保存后，独立144 MHz实现恢复通过（8725 LUT、5128 FF、WNS +0.163 ns），保持短测收益并另跑196次ISA。组合配对位流已通过，自己的双种子6000轮长测正在运行，不将旧完整分数套入新资源数。见 `LOAD_USE_ZERO_OFFSET.md`。

进一步的BEQ/BNE专用前递在141.75 MHz取得8526 LUT、5123 FF、WNS +0.193 ns；2105344次定向比较、196次外部ISA及CPU/SoC回归通过。两种十轮CoreMark周期不变，但SoC增加21周期，不宣称所有工作负载无代价；该新核心尚无独立双种子6000轮成绩。仅更换PLL的144 MHz性能PDS也通过（8634 LUT、5134 FF、WNS +0.210 ns），四频点厂商PLL模型与双短测通过；独立6000轮性能和验证均通过，RTL投影3.072866512 CoreMark/MHz、0.051250032 CoreMark/LUT；尚未实板。见 `LOAD_USE_EQUALITY_BYPASS.md`、`CLOCK144.md`。

本轮新增四个独立候选完成135 MHz时序、CPU/SoC及合计784次外部ISA核验：仅压缩LRU的分支专用前递组合为8640 LUT、5125 FF、WNS +0.361 ns；增加乘法进位保存并未进一步改善该组合的资源与时序。随后该LRU组合的实际141.75 MHz性能/验证两份PDS位流均通过（8662 LUT、5138 FF、WNS +0.033 ns）。两份独立绑定的6000轮RTL长测均通过（1952574242/1957402139周期），本候选仿真投影3.072866512 CoreMark/MHz、0.050286173 CoreMark/LUT；尚未实板，不上传GitHub。见 `MUL_CARRY_SAVE.md`、`CLOCK141750.md`。

本轮完成双种子非侵入退休跟踪，并实现分支专用加载前递：相对全停顿版，十轮性能少132099周期，但仍比原无停顿版多1.9615%，不宣称执行效率全面提升。候选135 MHz种子1通过（9271 LUT、5724 FF、WNS +0.119 ns），关键路径转到乘法结果；2105344次定向比较、196次外部ISA及相应拒绝控制通过。尚无该候选6000轮长测、配对位流或实板成绩，生产输入与GitHub不变。见 `LOAD_USE_PROFILE.md`、`LOAD_USE_BRANCH_BYPASS.md`。

关键路径后续隔离验证：缓存碰撞分解与两种并行前递核心均保持短测拍数，但135 MHz种子1分别为WNS -0.192/-0.279/-0.345 ns，未采用；三候选合计588次ISA及24个拒绝控制已审计。既有全局加载停顿参数的十轮执行代价为+6.08993%，短跑代理值约2.94585，不是正式分数，下一步先分类加载依赖再研究选择性停顿。生产源不变、不上传GitHub。详见 `CACHE_COLLISION_FORWARD.md`、`FORWARD_PARALLEL.md`、`LOAD_USE_COST.md`。

LRU存储隔离实验完成：直接数组原生映射将576个LRU触发器替换为576位小型RAM，功能差分、短仿真及外部ISA保持基线执行拍数；但135 MHz种子1/7/5均时序失败（最佳仍差0.010 ns）。仅压缩I-cache的组合也失败，未产生新合格分数，生产输入不变、不上传GitHub。详见 `CACHE_LRU_STORAGE.md`。

同步可写数据缓存H1候选在135 MHz/种子7通过：7437 LUT、4934 FF、WNS +0.014 ns，比通用H1少690 LUT。80种差分、13个功能拒绝、CPU集成及196次外部ISA通过；性能/验证位流配对与两份独立绑定本版的6000轮长仿真均通过。仅仿真投影为3.082968316 CoreMark/MHz、0.055963523 CoreMark/LUT，资源效率较通用H1提升9.2779%，完整执行拍数不变；尚未实板确认，不改生产输入，不上传GitHub。详见 `CACHE_SYNCHRONOUS_WRITABLE.md`。

同步缓存H3组合在135 MHz/种子1取得7528 LUT、4930 FF、WNS +0.094 ns，性能/验证位流配对、196次ISA及两份独立6000轮长仿真均通过。仅仿真投影为3.093382502 CoreMark/MHz、0.055473783 CoreMark/LUT；相对H1执行效率提高0.337797%，资源效率降低0.875106%，不能称三指标全面改善，尚未实板确认。详见 `SYNCHRONOUS_WRITABLE_H3.md`。

指令缓存16/32 KiB扩容已完成容量、CPU/SoC及392次外部ISA正例核验；10轮性能拍数分别降低1.224483%/1.412202%，但135 MHz种子1分别为9260/13610 LUT、WNS -0.191/-0.769 ns，未取得新的合格分数。已基于实际路径开始隔离MMIO载荷使能实验，生产RTL不变。详见 `INSTRUCTION_CACHE_CAPACITY.md`。

MMIO载荷使能优化与16 KiB指令缓存组合在135 MHz取得9220 LUT、5726 FF、WNS +0.117 ns；性能/验证PDS配对及各自6000轮长仿真均已核验通过。仅仿真投影3.133303445 CoreMark/MHz、0.045878087 CoreMark/LUT；相对8 KiB H3执行效率提高1.290527%，资源效率降低17.297713%，仍满足0.031模型门槛，尚未实板。8 KiB同改动种子1未通过时序，不作泛化。详见 `MMIO_READY_PAYLOAD.md`。

后续顺序PC预计算两候选完成69024个定向边界/优先级检查、11个编译故障拒绝、CPU/SoC和392次外部ISA核验，短测拍数不变；但135 MHz种子1的WNS分别为-0.034/-0.021 ns，均未采用。完整记录见 `FETCH_PC_PRECOMPUTE.md`，不把局部逻辑调整或失败布局称为新性能成绩。

通用H1/C2完整135 MHz性能/验证6000轮通过：执行拍数与旧分立H1相同，8127 LUT下资源效率仿真投影0.05121209827（提高0.66445%），执行效率投影3.0829683161 CoreMark/MHz。标签提前读取实验保持命中拍数；只读/双缓存版本均因135 MHz时序失败而拒绝。全部隔离、未板测、不上传GitHub。详见 `CACHE_TAG_PIPELINE.md`。

局部历史宽度筛选：六组H/C组合完成同固件短测；H3/C2完整6000轮性能对照再少6552000周期（0.337%），但135 MHz增加145 LUT、资源效率仿真投影下降约1.410%，不宣称全面改善。通用H1与H3的135 MHz性能/验证位流均通过（8127/8326 LUT）；H2种子1/7各差5 ps，种子5差27 ps，三者均拒绝。H2/H3共392次外部ISA通过；H3完整6000轮验证及独立绑定通过，本轮任务已全部终结，未板测、未修改生产输入、不上传GitHub。见 `BTB_HISTORY_WIDTH.md`。

局部分支历史隔离候选：同固件6000轮性能RTL仿真1980380679→1946176342周期（减少1.727%，同频吞吐提高1.758%），CRC与退休指令相同，两端各自重新绑定合格PDS输入。132/135 MHz种子7性能、验证位流均通过，分别8063/8181 LUT、WNS +0.071/+0.026 ns；135 MHz种子1失败保留。完整6000轮validation仿真也通过；本轮任务全部终态。CPU差分与196次外部ISA通过；未替换生产BTB、未板测、不更新正式成绩，也不上传GitHub。见 `BTB_LOCAL_HISTORY.md`。

隔离优化记录：单热ALU选择候选的53440组定向比较、六个运行变异及两种CoreMark短测通过，执行拍数不变；但132/135 MHz均时序失败且LUT增加，故不采用。20份生产输入保持原合格版本，不上传GitHub。见 `ALU_ONEHOT_OUTPUT.md`。

当前本地合格候选：同步I-cache、Cache扇出32及保留ALU高段预计算版（680F03DF / 47E2A544），132 MHz/种子7为8090 LUT、5021 FF、WNS +0.102 ns；135 MHz/种子1为8222 LUT、4989 FF、WNS +0.003 ns。各自性能与验证6000轮固件的位流均已本地通过，20份输入和原始报告重新核验；18 DRM、4 APM。全回归和196次外部ISA通过，两种短测周期不变。135 MHz仅3 ps裕量，不等于长期稳定性；尚未板测，不更新正式CoreMark/LUT。旧同步Cache时序失败和D66、AC24结果保留为历史记录。后续只在用户明确要求时上传GitHub。详见 `ALU_KEPT_PRECOMPUTE.md`。

只读Cache裁剪候选的132 MHz/种子1性能与验证位流均已本地通过：9236 LUT、5064 FF、WNS +0.082 ns；相对同条件C3少1041 LUT（约10.13%），多28 FF，裕量增加0.051 ns。完整回归、32种对照、13个运行控制及196次外部ISA通过，短测周期不变；三组135 MHz仍失败。全部本地任务终态，尚未上板，不更新正式CoreMark/LUT。本轮不上传GitHub。见 `CACHE_READONLY_WRITEBACK.md`。

本地已测更新：折叠BTB与分段ALU版在132 MHz完成两次性能6000轮及一次验证6000轮，两次性能UART逐字节一致。执行效率3.0297205298 CoreMark/MHz（较上一132 MHz +0.5559642%），吞吐399.9231099346 CoreMark；资源效率0.03862871727 CoreMark/LUT（-0.0170873%，仍高于0.031）。10353 LUT、5023 FF、WNS +0.103 ns；主频不变，不能称三指标全部改善。完整回归和外部ISA测试集合通过，135 MHz仍未过时序。设备已释放，本轮不上传GitHub；证据见 `HARDWARE_132MHZ_CARRY_SELECT.md`。以下按阶段保留历史记录，不替代本次绑定源码的结果。

当前源ILA：独立Target132Kept配置已原生确认109路、1024深度，132 MHz/种子7性能与验证插核均通过（9084 LUT、6876 FF、WNS +0.095 ns）。Windows/WSL各32项分析测试、67项PowerShell契约通过；两份位流均已终态并通过成对审计，尚无本版实板波形。见 `ILA_TARGET132_KEPT.md`。

历史Target132Carry源ILA进度：Target132Carry的109路映射、专用分析语义和拒绝测试完成；默认/种子1/种子7的132 MHz插核实现均失败，最好WNS -0.082 ns，均未烧录，不影响已测非插核成绩。43项PowerShell契约、21项ILA分析、8项报告及6项频率门槛测试通过；下一步考察独立地址生成路径。见 `ILA_TARGET132_CARRY.md`。

132 MHz实板更新：实验箱2完成两次性能6000轮及一次验证6000轮，执行效率3.0129694974 CoreMark/MHz、吞吐397.7119736614 CoreMark、资源效率0.03863531899 CoreMark/LUT。10294 LUT、5041 FF、4 APM，WNS +0.001 ns；相对已测126 MHz，频率/吞吐提高4.7619%、资源效率提高3.8867%，执行效率不变，增加86 LUT和234 FF。极小正时序裕量不等于长期稳定性或物理极限。设备已释放，未追加上传GitHub。详见 `./HARDWARE_132MHZ.md` 和 `./CACHE_ADDRESS_FANOUT.md`。

历史筛选：MMIO载荷、除法余数清零实验均未取得联合优势，已隔离；上一轮结束时曾恢复全部20份126 MHz生产输入。本轮在此基础上继续修改M单元与PLL，不能沿用“当前全部恢复”的说法。

126 MHz 实板更新：同一实验箱2完成两次性能6000轮和一次验证6000轮，3.0129694974 CoreMark/MHz、379.6341566767 CoreMark、0.03718986645 CoreMark/LUT；10208 LUT、4807 FF、4 APM，WNS +0.128 ns。相对上一实板120 MHz前递版，主频提高5%、资源效率提高约4.60%，增加39 LUT；执行效率微差不算结构收益。原120 MHz达标记录保留，物理极限和全项目验收仍未完成。 详见 `HARDWARE_126MHZ.md` 与 `CACHE_LOOKUP_DATA.md`。

前递数据资格修订实板更新：120 MHz、3.0129645923 CoreMark/MHz保持，LUT降至10169、FF为4821，WNS +0.191 ns，资源效率提高到0.03555470067 CoreMark/LUT（+1.14072%）。两次干净性能4000轮与一次验证4000轮均通过，完整回归及外部ISA通过；135 MHz时序失败未上板。新core源码需要独立ILA映射，不自动继承旧窗口。详见FORWARD_DATA_QUALIFICATION.md，未再次上传GitHub。

2026-09-07低位乘法同拍试验：同固件短跑周期减少约2.815%，功能全回归及外部ISA通过，但120 MHz PDS WNS=-2.291 ns，拒绝上板；候选隔离、全部20份达标生产输入哈希恢复一致。详见FAST_LOW_MUL.md，不用失败时序的名义频率计算新成绩。

依据：`topics/紫光同创.pdf` PDF 第 10–11 页（印刷页 8–9），以及指定历史会话。AI 加速暂缓，其他要求不降级。

达标配置ILA更新：ILA_TARGET120.md记录120 MHz原生109路插核、累计四次完整性能长测及一次验证种子长测，并取得链表、矩阵、状态机真实局部窗口；不借用旧27 MHz波形填补，也不声称算法所有路径均覆盖。

新增优化约束：资源效率至少0.031 CoreMark/LUT，在此基础上联合优化执行效率与频率。check_performance_target.py已增加精确整数资源门槛及边界反例；当前未插核达标版0.03515369481、性能插核版0.03224721290均满足。既有120 MHz/3.0门槛保持，物理极限尚未证明。

独立GPIO诊断新增：GPIO_DIAGNOSTIC.md说明UART负对照、KEY输入/挂起/中断/LED联合观察与真实板级映射回归；诊断不替代CoreMark固件，也不把边界扫描虚拟按键直接当作独立实体输入验收。修订版已完成120 MHz实板9条命令/360字节核验，UART单独跳变未产生GPIO中断；独立KEY输入正例仍缺，详见该文末尾修订版结果。

2026-09-06新增用户硬目标：120 MHz下至少3.0 CoreMark/MHz，同时优化执行效率、频率及资源效率。当前实板已达到3.0129645923 CoreMark/MHz、0.03515369481 CoreMark/LUT，性能4000轮重烧复测两次和验证4000轮一次均通过；详见HARDWARE_120MHZ_TARGET.md。该数值指标不等于全部赛题验收，GPIO、ILA新映射、电气约束和物理极限仍未完成。下列按时间记录的早期未达标结论保留历史含义。

12:39候选更新：标准M扩展默认关闭，开启后120 MHz实板1.24895992 CoreMark/MHz，5032 LUT与4 APM，性能4000次两遍及验证4000次一遍通过，仍未达标。RV32I严格基线保持，额外ISA和资源代价详见M_EXTENSION.md；旧ILA映射不适用于该新候选。

13:10候选更新：新增默认关闭的FETCH_OVERLAP路径，完整仿真回归、上游RV32UI/RV32UM与120 MHz PDS通过，正式硬件长测尚缺。5200 LUT及收窄的时序余量如实保留，详见FETCH_OVERLAP.md；未把短仿真换算当作正式CoreMark成绩。

后续候选更新：默认关闭的FAST_DCACHE_READ读响应优化已完成本地回归与120 MHz可实现配置筛选，详见FAST_DCACHE_READ.md。直接前递时序失败，寄存加载配置通过；未上板，不自动完成性能、ILA或电气验收。PDS新增逐构建源码及约束快照以保留优化输入。

14:39候选更新：默认关闭的EARLY_D_REQUEST已通过最终完整回归、外部RV32UI/RV32UM及120 MHz PDS，短跑性能/验证CRC均通过；首版失败由地址选择解耦修正，代价及证据见EARLY_DATA_REQUEST.md。新位流未上板，不自动完成性能、ILA和电气验收。

15:10候选更新：乘积提前响应和非加载前递资格精简完成最终全回归及外部ISA验证；小缓存和大缓存组合均通过120 MHz PDS，失败版本及三指标折衷见MUL_EARLY_RESPONSE.md。原实板记录不被新仿真覆盖，性能/验证新位流仍需真实板卡长测，其他验收缺口不变。

BTB容量候选更新：BTB容量成为显式可追溯参数，默认16项保持；64/128项完成完整回归、两套外部ISA测试及120 MHz PDS，三指标对照见BTB_CAPACITY.md。新配置字、清单及校验器已同步，旧ILA映射继续拒绝未验证容量；不把短仿真和本地实现冒充实板验收。

数据请求重叠候选更新：DATA_OVERLAP默认关闭，新增读写交接、Cache/MMIO响应归属、背压及错误恢复测试；64项BTB组合完成全回归、外部ISA及120 MHz实现。执行/资源代理指标和故障注入证据见DATA_OVERLAP.md。新位流未上板，原生ILA新映射、GPIO独立输入、电气约束及性能硬目标仍未自动验收。

乘法器内部修订：并行半字乘积在请求沿寄存，保持单事务、背压和精确取消；最终全回归、14组中断、外部RV32I/M及120 MHz性能/验证位流通过。详见MUL_REQUEST_CAPTURE.md。此内部时序变化不新增配置位，必须按源码快照区分，所有新实板、ILA、电气约束与3.0性能缺口保持未完成。

加载前递修订：完整高位地址拒绝先于截断标签；按指令类缩短握手资格且断言与完整异常等价；MMIO请求保持和复位取消；错误缓存响应仍为零。最终全回归、正负变异及外部ISA通过，直接前递120 MHz实现7007 LUT、4146 FF、WNS +0.076 ns，同源码B1对照完成。边界行为、周期/面积权衡及位流证据见CACHE_ADDRESS_BOUNDS.md；本轮不将内部时序通过视为新实板、ILA、GPIO输入、电气约束或3.0成绩验收通过。

BTB存储修订：完整PC/目标高位检查在截断前执行；目标按字地址保存；类型数据不复位但有效位仍复位。默认全地址、有界64/128/256、逐位边界与四个变异均验证，最终全回归及有界CPU外部RV32I/M通过；64项性能/验证位流120 MHz通过，6935 LUT、4080 FF。详见BTB_ADDRESS_BOUNDS.md；不得将面积减少或时序通过替代正式CoreMark、ILA、GPIO和电气验收。

DCache写命中快路径：独立开关默认关闭，仅作用于数据Cache；旧值响应、全部16种字节掩码、零掩码不置脏、背压稳定、连续重叠、提交前复位、只读及错误路径均有测试。完整回归、额外128项候选测试、外部RV32I/M和故障注入通过；128项BTB + 写快路径性能/验证实现均满足120 MHz（WNS +0.165 ns，7183 LUT、4130 FF），64项写快路径WNS -0.082 ns保留为失败点。详见FAST_DCACHE_WRITE.md；该组合尚未上板，不能替代正式长跑、独立GPIO输入、ILA、SCBV及电气约束验收。

异常元数据复用：保持异常优先级及CSR提交，删除重复的EX→MEM异常值保存。3249项定向检查、八个错误值来源变异、完整回归、128/256项候选补充差分/SoC及64/128/256项外部RV32I/M通过；128/256项每侧2 KiB的性能/验证实现均通过120 MHz，仍未上板。64项失败和资源效率代价保留，详见TRAP_VALUE_REUSE.md；不得以8 KiB短测的周期预算线索替代120 MHz物理实现与正式长测验收。

非对称Cache：ICACHE_SET_BITS默认0继承数据容量，配置字新增兼容的独立指令容量字段。几何/配置实际读回、错误参数传递变异、全回归、非对称CPU/SoC和外部RV32I/M通过；同时纠正缓存差分入口的独立读写开关映射，历史受影响覆盖不可追认。8/2 KiB性能/验证120 MHz实现通过，但持续短测仍未达到周期预算，正式长测、ILA新映射、GPIO输入与电气验收不因此通过。资源效率退步与8/4 KiB失败证据见ASYMMETRIC_CACHE.md。

## 实现与验证顺序

| 要求 | 设计方案 | 完成证据 | 当前状态 |
| --- | --- | --- | --- |
| RV32I | 严格译码、32 个寄存器、整数 ALU、字节/半字/字访存 | 自有差分与固定上游 RV32UI 测试 | 41个外部测试×4配置共164次通过，四个拒绝控制通过；ma_data透明未对齐访问不适用，不冒充完整ISA认证；见 EXTERNAL_ISA.md |
| 至少三级流水线 | IF / ID / EX / MEM / WB，前递、load-use 暂停与冲刷 | 冒险、访存反压、跳转错误路径无副作用测试 | 已实现，随机总线延迟与参考模型通过 |
| UART / GPIO | 27 MHz参考，可选PLL倍频，115200 8N1，LED 与按键映射 | 全字节收发、FIFO、MMIO、C 输出仿真 | 已实现；27/54 MHz实板UART自检闭环通过，GPIO 输入仍待独立实板验证 |
| 双路 I/D Cache | 分离两路组相联，行填充，D-cache 写回与写分配 | 冷缺失、命中、冲突替换、脏写回、反压测试 | 已实现，差分及 PDS 通过；含 Cache/FENCE.I 的实板 C 自检通过，全面硬件边界测试待补 |
| 突发总线 | 独立于 CPU 的行请求/逐拍响应握手 | 多拍计数、末拍、背压与仲裁公平性测试 | 已实现，轮转仲裁与片上 RAM 集成通过；不是 DDR 后端 |
| 动态分支预测 | BTB + 两位饱和计数器 | 命中、别名、误预测恢复与性能对比 | 两配置差分通过；同箱同固件各两次长时CRC通过，开启后周期降低16.1019% |
| 异常/中断 | M-mode、Zicsr、mtvec/mepc/mcause/mtval/mstatus/mie/mip、mret | 精确异常、访存错误、定时/外部/软件中断、返回测试 | CPU 与优先级单元通过；SoC仿真中GPIO/UART外部中断均通过，实板软件/定时/UART外部中断自检通过，GPIO按键实板事件仍未验证 |
| 软件工具链 | 真正 riscv32-unknown-elf GCC、RV32I / ILP32 裸机启动与链接 | GNU 源码固定哈希、目标/ELF/库检查，完整回归 | GCC 10.2.0 + Binutils 2.35 从源码构建并接入；完整回归通过，90 MHz性能固件与已测镜像完全一致；见 TOOLCHAIN.md |
| CoreMark v1.0 | 固定上游版本、合法种子与CRC、不少于10秒 | 实板UART、迭代数/周期/频率/CRC与构建哈希 | 120 MHz候选两次性能4000轮和一次验证4000轮长测通过，3.0129645923 CoreMark/MHz、361.5557510765 CoreMark；此前消融保留历史证据，长期稳定性及进一步联合优化待续；见HARDWARE_120MHZ_TARGET.md |
| PDS | Windows ADS 全流程，PG2L200H -6 FBB676 | 新 CPU 位流、setup/hold、资源报告 | Board/RemoteLab两套UART约束已生成位流；27/54/75.6/81/90/99/108/135/162 MHz内部时序通过，其中75.6/99/135 MHz未上板；216/270 MHz违反时序，已拒绝采用；最高可达频率、异步I/O和SCBV边界仍需继续核实 |
| 应用场景 | CPU 控制的 GPIO 软件波形采集器 | 触发、采样、串口导出与真实输入演示 | 已实现；箱5两次各256点实测独立解码0x55/0xAA，校验通过；实板KEY边沿与长期复测待补 |
| 分析文档 | 流水线效率、Cache/预测开关消融、ILA 波形 | 原始测量与可复现报告 | Cache与预测器开关长时消融已完成；109通道1024深度原生ILA六个算法窗口通过时序一致性检查，进一步优化及构建打包待续 |

## 已核实边界

SCBV原厂表格与板卡电源资料已核查，证据及尚缺的远程板配置网络见 `CONFIGURATION_ASSURANCE.md`；没有猜测电压设置，也没有将该待办误标完成。

- 工作分支为 DYH。原流水灯目录保留不动，不将其上板结果当作 CPU 验证。
- 仓库 LICENSE 已存在用户修改，不覆盖，不自行提交或推送。
- MES2L676-200HP 手册：时钟 D18，27 MHz；KEY0 C22；UART RX B24、TX C24。
- 其余引脚与电压约束必须逐项对照原厂例程，不能使用 100H 工程代替。
- WSL Ubuntu-22.04 使用 Icarus 11.0 与 Verilator 4.038。原系统 RV64 multilib 保留；工程现在显式调用源码构建的真实 `riscv32-unknown-elf-gcc` 10.2.0，目标、默认 ISA/ABI、32位库和完整回归已核实，见 TOOLCHAIN.md。
- 只有仿真通过不代表实板通过；CoreMark 不以估计值、短时运行或未校验 CRC 作为正式成绩。

## 当前单元验证

- `pwsh -NoProfile -File cpu/scripts/run_tests.ps1`：译码/ALU 13,124 项、BTB 14 项、machine CSR 30 项检查通过，日志在 `cpu/build/unit-tests.log`。
- `rv32_decode` 穷举 OP/OP-IMM 的 funct7/funct3 合法性，覆盖访存宽度、跳转立即数和特权指令代表编码；并非完整 ISA 认证。
- `rv32_alu` 以固定种子执行 10,000 次算术逻辑结果检查，现已另有 CPU 级独立参考模型差分验证。
- `rv32_btb` 验证两位计数饱和、同索引不同 tag 替换、无条件跳转、失效优先级和未对齐访问拒绝。
- CPU 顶层与全部子模块通过 Verilator 4.038 `--lint-only --Wall`，不使用告警抑制。
- 仓库级 `git diff --check` 检出原有 LICENSE 换行问题；未修改该用户文件。当前新增文件单独检查。

## 下一步

2026-09-06 10:57：最高满足所设时序约束且已实板验证的测试点提升到180 MHz（显式LOAD_USE_BUBBLE=1）。箱3性能1000次重复两次一致，验证种子一次通过，4000次持续运行两次各60.9935秒一致，65.9430 CoreMark，详见 `HARDWARE_180MHZ.md`。保持默认参数与162 MHz基线，不将该结果称绝对Fmax或多小时稳定性；GPIO独立输入、SCBV/外部I/O和最终逐条审核仍未关闭。

2026-09-06交付入口新增 `FINAL_REPORT.md` 与 `DELIVERY.md`：汇总主成绩、消融、关键算法ILA和应用，并提供带逐文件哈希的工程快照打包器。快照明确不代表最终验收；load前递实验已有独立实测但在162 MHz下无收益，默认关闭，详见 `LOAD_FORWARD_EXPERIMENT.md`。

远程实板交互自检已通过，记录见 `HARDWARE_SELFTEST.md`；CoreMark 移植和基线分别见 `COREMARK.md`、`COREMARK_RESULTS.md`；波形应用两组实测见 `SCOPE_APPLICATION.md`；Cache与预测器重复消融见 `HARDWARE_CACHE_ABLATION.md`、`HARDWARE_PREDICTOR_ABLATION.md`；真实ILA分析见 `ILA_RESULTS.md`。继续完成构建打包、长期稳定性、最高实测频率与优化。所有当前测试通过仍不代表比赛工程全部完成。

## 当前 CPU 验证

- `cpu/scripts/validate.ps1` 统一运行单元测试、CPU 测试、独立 Python 参考模型、完整 16 KiB 存储器对比、严格 RTL lint 与参考检查器自身的 6 项有效/变异测试。
- CPU 自检包含固定种子 20260906 的 256 个随机操作，混合算术、移位、分支和不同宽度访存；预测关闭/打开各使用 3 个总线随机种子。
- 无缓存六次运行各有 793 条退休指令、13 次陷入事件；每条退休 PC、指令、写回值和陷入原因均由独立模型核对。自修改代码改变函数指令后必须经 FENCE.I 才重新执行。
- 该汇编测试的 13 次陷入包括 12 个同步异常场景及 1 次定时中断；另有 C SoC 测试验证三类中断各一次。两者均为仿真，不能据此声称 SoC 实板验证通过。
- 程序刻意写 minstret 测试写入优先级，因此日志中的 `retired` 是可写 CSR 的当前值，不是整个仿真的退休事件总量；总事件量见 reference 日志。
- 当前无缓存六组仿真为 6,662–6,994 周期，采用随机延迟存储模型，不是 CoreMark 成绩、实板主频或最高工作频率。

## 当前存储系统验证

- Cache 单元：5,906 项检查；只读 Cache：3,188 项。每种配置包含 512 次随机访问及最终完整内存对比，另覆盖读错误、早/晚 last、写回错误、维护失败重试及零字节使能。
- 突发 RAM/仲裁：816 项检查，26 次命令。包括两主机并发轮转、命令等待时不更换归属、应答反压、非法写帧无副作用。
- `run_cached_tests.ps1` 的四种配置均通过独立指令/异常/16 KiB 最终内存比对；小容量 Cache 强制替换，默认容量验证命中路径。
- 四种配置分别执行 5,483 / 5,356 / 4,709 / 4,587 个仿真周期（2 组无预测 / 2 组有预测 / 16 组无预测 / 16 组有预测），包含结束后的维护等待，不能直接作为正式 CPI 或 CoreMark 对比。
- 已观察且强制检查 MEM 前递、load-use 前递、I/D 命中与缺失、脏写回。集成回归捕获并修复 FENCE.I 与前端待接收响应之间的死锁。
- `validate.ps1` 同时对 CPU 与完整存储系统运行无告警豁免的 Verilator lint。缓存仿真报告位于 `cpu/build/cached-tests.log`。

## 文件布局

`rtl/` 可综合硬件；`sim/` 自检平台；`sw/` 裸机软件；`scripts/` PowerShell 7 与跨平台工具；`constraints/` 板级约束；`docs/` 设计和证据说明。构建产物在 `build/`，不入版本控制。

独立直接分支提前恢复候选完成196次ISA、随机/精确中断/SoC回归及双短测，性能/验证周期降低1.6708%/1.7059%；实际148.5 MHz PDS为8798 LUT、5120 FF、WNS -0.176 ns，仍拒绝，不替换已合格carry16基线，不公布候选完整分数或上传GitHub。详见 `docs/EARLY_DIRECT_REDIRECT.md`。

8位分组地址进位候选在不改变直接分支方案周期和退休轨迹的前提下通过约1016万算术组合、196次ISA及8次SoC回放；实际148.5 MHz为8825 LUT、5121 FF、WNS -0.091 ns，仍拒绝。独立146.25 MHz两个实际布局种子分别以WNS -0.036/-0.191 ns拒绝，均不采用。后续RAM分支地址域单行候选已通过8192个地址探测、24组原/新交接配对、8种严格lint、2次缓存CPU独立参考和相同双短测；新196项ISA与8次SoC已通过，但实际146.25 MHz为8737 LUT、5121 FF、WNS -0.167 ns，拒绝，见 `docs/DCACHE_RAM_DOMAIN.md`。随后独立有效位分组候选通过219399次定向检查、14组缓存配对、原196项ISA及额外I9/D6目标98对196次、8次SoC和相同双短测；实际为8771 LUT、5132 FF、WNS -0.036 ns，仍拒绝，见 `docs/DCACHE_VALID_BANKS.md`。没有新候选完整分数。见 `docs/EARLY_DIRECT_CARRY8.md`；生产RTL不替换，不自动上传GitHub。

缓存入口错误分类寄存重排候选通过16组边界/错误配对、14组完整缓存配对、常规196项ISA、实际I9/D6额外98对196次、4组SoC配对及周期完全相同的双短测；实际146.25 MHz为8989 LUT、5170 FF、WNS -0.194 ns，仍拒绝。最差路径转到地址高位的MMIO/RAM路由控制，见 `docs/CACHE_ERROR_RETIME.md`。不替换合格基线，不产生新完整分数，不自动上传GitHub。

MMIO影子请求候选通过60组协议配对、24组原交接配对、常规196次ISA、目标配置98对196次ISA、8次SoC及周期不变的双短测；实际146.25 MHz为8876 LUT、5177 FF、WNS -0.292 ns，时序门禁拒绝。最差路径转到早期分支比较及I-cache控制，见 `docs/MMIO_SHADOW_ACCEPT.md`。不替换合格基线、不产生新完整分数、不自动上传GitHub。

早期分支并行字节比较候选通过786624组比较输入、7424项分支场景、常规196次ISA、目标98对196次ISA、8次SoC及周期不变的双短测；实际146.25 MHz为8961 LUT、5176 FF、WNS -0.372 ns，拒绝。原生比较结构确实保留，但最差路径延伸至PC更新进位链，见 `docs/EARLY_COMPARE_BYTE.md`。不替换合格基线、不产生新完整分数。

陷阱向量结果边界候选从实际网表确认并隔离了重定向选择与向量加法链，原/新589824项向量检查、常规196次ISA、目标98对196次ISA、8次SoC及周期不变的双短测通过；实际146.25 MHz为8933 LUT、5169 FF、WNS -0.109 ns。相对父候选减少28 LUT、7 FF、裕量改善0.263 ns，但仍拒绝资格，见 `docs/TRAP_VECTOR_BOUNDARY.md`。不替换合格基线、不产生新完整分数。

整字加载地址直接前递候选完成两种6000轮完整仿真及同固件实际PDS来源绑定：146.25 MHz、8895 LUT、5185 FF、WNS +0.055 ns，性能/验证分别1885980108/1888935654周期，CRC均正确且各超过10秒。仅就本地RTL/PDS而言为3.181369716 CoreMark/MHz、465.275321 CoreMark、0.052307512 CoreMark/LUT；相对既有148.5 MHz carry16基线执行效率提高1.7036%、吞吐提高0.1627%，但资源效率下降2.2921%，不是全面优于旧基线。见 `docs/WORD_LOAD_ADDRESS.md`。生产RTL不替换，没有新上板结论，不自动推送GitHub。

以已通过的3.181370版本CPU为基础，151.2 MHz定时比较拆分布局种子2的双固件PDS及各自绑定的6000轮完整仿真均已通过：8979 LUT、5176 FF、WNS +0.033 ns；本地RTL/PDS为3.181369716 CoreMark/MHz、481.023101 CoreMark、0.053572013 CoreMark/LUT，三项门槛同时达标。双种子CRC、超过10秒的计时间隔、完整周期/退休/缓存事件及34项物理、28项完整结果拒绝控制通过；此前纯升频和布局种子1的失败报告保留。见 `docs/TIMER_COMPARE_SPLIT.md`，接受基线为 `build/timer-compare-split-seed2-accepted-baseline.json`。后续升频不得降低相对本版的任一效率，不替换生产RTL、不冒充实板结果、不自动推送GitHub。

## 无外设变体：频率绑定纠错（2026-09-09）

`build/peripheral-partition/pds/20260909-194559-786ec275/result/resource-summary.json` 证明 144 MHz 实现通过本地 PDS：7756 LUT、3430 FF，setup WNS +0.105 ns，All Constraints Met。这只证明该构建的物理时序与资源，不证明 CoreMark 运行结果。

撤回此前本条中的 501.143188 CoreMark、3.480161 CoreMark/MHz 和 0.064614 CoreMark/LUT 配对结论：501.143188 来自另一份 **157.5 MHz** 固件的完整 RTL 仿真，不能除以 144 MHz，也不能直接与 144 MHz 构建的 LUT 配对。该旧仿真的 6000 轮计分周期为 1885688608，正确执行效率为 `6000 * 1000000 / 1885688608 = 3.181861509 CoreMark/MHz`。

144 MHz 固件当前只有 BuildOnly 与 PDS 证据，缺少绑定同固件、同 RTL 的完整性能/验证运行及实板读回，因此本版本三项联合性能仍不合格；144 MHz 低于已通过版本的 157.5 MHz，亦不满足用户的不降频优化约束。144/146.25/148.5 MHz 仅保留为诊断实验，不替换主基线、不宣称新跑分或目标完成。
