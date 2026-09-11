# Specialized control-instruction commit predicates

Parent: `../full_mul_precompute_clock154285`. Preserve compact MUL precompute, GPIO, UART and full 42-data/33-trigger/1024-depth ILA. Configured clock remains 154285714 Hz. The accepted DC90363D baseline is not modified.

The parent full-build critical path runs from cache request-error reduction through memory response and generalized `mem_fire` into predictor counter write enables. Branches, CSR operations, MRET and FENCE.I cannot also be loads or stores. This experiment specializes their commit enables using the mutually exclusive decoded instruction classes, retaining exception suppression and FENCE.I maintenance acknowledgement. There is no pipeline stage, predictor-training delay or intended cycle-count change.

Only four CPU connection expressions change. All other physical sources remain byte-identical to the parent, including the GPIO/UART RTL, PLL and constraints. `source-inputs.json` records the exact delta. Source-extracted four-state predicate equivalence, decoder exclusivity, live-core assertions, existing precise-exception regressions, matched CoreMark pairs and fresh full-ILA physical qualification must pass before promotion.

No timing improvement or benchmark score is claimed by this structural change alone.

## Current local results (September 10, 2026)

The user now sets two numerical hard floors: CoreMark at least 501.0657302224314 and complete-system CoreMark/LUT at least 0.053452712846429634. Execution efficiency remains an optimization objective, not a separate nondecreasing admission gate. Clock tradeoffs are allowed. The new score/resource policy is separate from historical comparison functions; six tests cover permitted execution-efficiency tradeoffs and exact rejection boundaries.

Both ten-iteration runs are unchanged against the same-clock parent: V0 20260910-195856-6bf511dd has 3060873 cycles; V1 20260910-195908-6ac62ce5 has 3065630 cycles. CRCs, retired counts and cache profiles match. Four specialization tests pass: exact source delta, 57344 source-extracted predicate comparisons with four-state bus inputs and initialized binary pipeline controls, 1179652 decoder-class checks across structured/random instructions and both M settings, and five rejected predicate mutations. These are not whole-core formal proofs.

Six live-core runs pass with the original control predicates checked every cycle and independent architectural traces. Fourteen precise M-extension interrupt/cancel/restart runs pass. GPIO passes two configurations with 2976 checks and three interrupts each; four SoC UART/fault cases pass. Pinned external RV32UI/UM tests pass 164 + 32 runs and four negative controls per suite; this is not ISA certification.

| Image | Ordinary PDS build | Full-ILA build | Full LUT / FF | Full setup WNS |
| --- | --- | --- | --- | --- |
| V0 | 20260910-195826-f8ada957 | 20260910-control-commit-seed2 | 9406 / 5004 | 0.000 ns |
| V1 | 20260910-201323-f511731b | 20260910-control-commit-v1-seed2 | 9406 / 5004 | 0.000 ns |

Both ordinary builds fail at -0.217 ns with 9046 LUT; those failures remain preserved. Both complete builds report All Constraints Met, retaining 42 data / 33 trigger channels and depth 1024. Zero reported setup slack is tight closure, not a demonstrated robustness margin. SCBV/electrical review is still open.

The two 6000-iteration RTL runs, 20260910-200328-351ec921 and 20260910-200355-357efcf4, pass at 1831572143 / 1834527689 cycles and 1649428424 / 1649775523 retired instructions. Their modeled timed durations are 11.8713009488 / 11.8904572655 seconds. Current firmware, RTL, physical wrapper parameters and full-ILA artifacts are independently bound for each seed.

The V0 **local RTL/PDS projection**, not a hardware score, is 505.4205959278995 iterations/s, 3.2758742389324493 iterations/(s * MHz), and 0.0537338503006485 iterations/(s * LUT). Relative to the accepted baseline: throughput +0.8691206448%, execution efficiency +2.9705608489%, resource efficiency +0.5259554459%. Total LUT increases by 32, but throughput increases proportionally more. The updated audit_joint.py writes build/local-joint-score-resource-qualification.json; the earlier three-floor receipt is retained separately.

## Local algorithm waveform evidence

capture_pipeline.py and audit_pipeline.py reproduce three source-bound 1024-cycle windows under build/ila-pipeline-rtl/control-commit. List/matrix/state windows have 728/482/552 WB events. Their exact 42-bit order matches the retained probe map. Observation leaves the entire short CoreMark result unchanged. SVGs and 16-cycle zooms are labeled RTL ONLY and use 154285714 Hz; the matrix zoom was visually checked. These windows neither read vendor ILA storage RAM nor prove global IPC or the cause of every stall. The existing user-approved local-ILA acceptance scope is retained; remote ILA acquisition is not introduced as a new requirement.

## Application and board-access gate

The inherited scope application assumed 27 MHz. The existing clock-aware application and 64-bit timeout implementation have been ported into this isolated candidate, and the builder now admits 154285714 Hz. Its local configuration uses 1234-cycle sampling and a 4628571420-cycle (30-second) timeout. The first current-source simulation completed two captures, EMPTY and TIMEOUT, but the old decoder clock allowlist rejected its output; that failed record remains intact at build/scope-current/20260910-203122-4b3efabf. The parser now admits the specific new clock with a seventh clock/time-axis test. Fresh run build/scope-current/20260910-204030-a5aef487 passes at 2705507 simulated cycles: UART 0x55, KEY transitions, two 256-sample captures with zero late samples, EMPTY and the 64-bit timeout. The timeout test deliberately advances the machine counter across 2^32 and then the remainder; it is not a real-time 30-second board measurement. Application-specific full-ILA physical implementation now passes; see the qualification update below. This does not constitute board validation.

The supplied Topic 1 PDF, pages 10-11 (printed pages 8-9), still requires the five non-AI tasks, an application scenario, performance/implementation analysis, and at least ten timed seconds for CoreMark. Numeric gates alone do not close all project requirements. Remaining local acceptance, application implementation artifacts, and electrical/constraint review must be checked before remote verification.

The user supplied Chrome debugging port 19476 and requires project qualification before remote-board verification. It has not been contacted under that updated instruction. The earlier tool-policy rejection of a new Chrome launch is historical; no workaround was attempted. No new board result, baseline replacement, Git commit or GitHub push is claimed.

## Application physical qualification update (September 10, 2026)

The scope application is now implemented with the same complete CPU/peripheral/ILA configuration. Ordinary source build build/pds/20260910-205544-c0e79deb completed synthesis but failed post-route timing at -0.217 ns with 9046 LUT; its failed result is preserved and is not admitted for board testing.

Full implementation build/ila/20260910-control-commit-scope-seed2-retry1 passes All Constraints Met at the configured 154285714 Hz, setup WNS 0.000 ns, 9406 total LUT and 5004 FF. Actual Inserter output verifies 42 data channels, 33 trigger channels, depth 1024 and cpu_clk. The scope firmware hash is E653E92458D0DB6ECF016EBB5932BC73DAEDB9ED2F791FD6A4B132574D79764A; bitstream SHA-256 is C66B103DCD1CCB92F5ED804E55489D424F109011E2A937AB090AC992D2928A9E. A second independent invocation of the physical auditor passes against the unchanged input hashes.

The preceding build/ila/20260910-control-commit-scope-seed2 directory preserves a failed Inserter command: native Tcl misread a Windows-style path. Only that failed owned Inserter process was stopped. run_scope_full_ila.ps1 now normalizes the native Inserter script argument to forward slashes. The fresh retry has its own synthesis-input copies, actual Inserter output, invocation times/PID, logs and bitstream; no failed result was rewritten into a success.

audit_scope_firmware.py explicitly binds the tested scope binary, clock, sample interval, 64-bit timeout and all six recorded application build sources. Scope and CoreMark validation modes are mutually exclusive; the original benchmark firmware checks remain strict. audit_binding.py checks the actual application's generated board wrapper and source snapshot. The current CoreMark joint audit still passes without changing benchmark sources or scores.

Twenty-five structural/provenance unit tests pass: six new scope tests, six new synchronizer tests, six existing wrapper tests and seven existing full-ILA qualification tests. The bounded synchronizer audit also passes on the actual scope netlist, not just the benchmark image. Results and limits are documented in LOCAL_ELECTRICAL_REVIEW.md. This does not establish complete CDC, reset or external electrical signoff.

Application RTL and physical implementation are now locally qualified within those stated scopes. Electrical evidence for the actual remote board and subsequent physical application/benchmark testing remain outstanding. Chrome port 19476 has not been contacted, the accepted baseline is unchanged, and no GitHub upload was performed.
