# Fetch-prediction payload capture optimization

## Latest physical step

Ordinary PDS completes with 9153 LUT / 4282 FF and WNS -0.320 ns at 151.2 MHz: timing fails. The full-ILA stage build/ila/payload-seed1 starts as PID 40928 after ordinary PDS exits. Its actual native 42/33/1024 mapping passes, and all twelve source/firmware/UART/native-channel tests pass in build/full-ila-tests.log. Final full-system timing/resources are pending. This update supersedes the older launch description below and does not qualify a new score.

## Scope and measured motivation

This candidate starts from the qualified full_redirect_clock151200 version, retaining its three-bit local-history predictor. Only rv32_core.sv changes, from 81671AD0A87EBD75F68D6351A85DAA21899CA42D27472B4C5B325F59EA8ABDEE to 10E46E6286F17F8DC25C619298EB5AA0F032939299CB7562A7EB818B5CE28A81. It does not stack the rejected four-bit predictor or remove GPIO, UART or the required ILA.

The ordinary four-bit-history timing report identifies a ten-level path from mem_result[1], through early branch comparison and flush control, to fetch_prediction[18].CE: 2.063 ns logic and 4.199 ns routing. Its full-ILA run has a different worst endpoint, raw_pair_relation[0].CE. This change targets one measured late-enable path; it is not evidence that every timing bottleneck is fixed.

## Payload lifetime reasoning

Fetch control, request acceptance, redirects, pending flags, discard behavior and next-PC selection are unchanged. Only prediction payload capture is separated from the frontend-flush/barrier guards. It captures while the fetch slot is idle, when a response can complete through normal acceptance space, or when an unsent redirect-primed request is accepted.

For a live normal response, the new capture condition matches the old capture opportunity. For a redirect-primed request, the invariant pending -> active and not sent and not discarded ensures capture before the response becomes eligible. Extra writes during an idle, discarded or blocked slot are allowed only because that payload cannot be consumed as a live instruction before a subsequent valid capture. This is a design argument backed by bounded simulation, not a formal equivalence proof.

change-receipt.json binds the exact three substitutions and both CPU hashes. The existing register reset is preserved. No clock, firmware, cache, predictor, peripheral or architectural feature parameter changes.

## Completed verification

- Four predictor/overlap combinations each pass 6000 randomized dual-core cycles, comparing bus handshakes, request addresses, fetch state, live IF/ID/EX/MEM metadata and retirement. Flushes, barriers, request delay, held responses and overlap are exercised. Each non-overlap case observes 312 held-response cycles; each overlap case observes 417, with 949 simultaneous response/request transfers.
- Extra internal payload updates are actually observed (329 or 371 cycles), while live metadata stays equal. Four compiled faults that drop idle, normal-response or redirect capture, or overwrite on every cycle, fail at live IF metadata comparison.
- All four predictor/overlap modes pass the existing 35-case / 444-check directed redirect suite, including request backpressure, early/error responses, stale-response drain, repeated redirects, barriers and reset. The cloned bench uses the actual RESET_VECTOR parameter name.
- Both complete ten-iteration CoreMark runs are byte-identical to the qualified parent's UART logs: V0 3004340 cycles and V1 3007840. CRCs, retired counts and profiling counters match. No execution-efficiency increase is claimed from this transformation.

The randomized test forces frontend controls and uses NOP responses; together with the directed suite and CoreMark it is bounded evidence, not exhaustive ISA/interrupt or physical-board validation. See build/payload-regressions.log and build/v0, build/v1.

## Physical validation

prepare_physical.py binds all twenty physical inputs, changing only the CPU, and verifies complete UART equivalence before staging. Ordinary PDS runs as PID 94344 at build/physical-project-complete/build/pds/20260911-030148-7fb9c108, using 151200000 Hz, V0 6000-iteration firmware and placement seed 1. Its final result is pending at this entry. Seven source-binding checks pass in build/physical-binding-tests.log.

Native discovery identifies core-local IF/EX/MEM valid nets and the parent alias board/soc/unused_pipeline_valid[1] for ID-valid. audit_full_ila.py proves the exact CPU output-port connection and the underlying register Q drivers before normalizing these names. The full-ILA runner preserves all 42 data / 33 trigger channels and depth 1024 and waits for the verified ordinary PDS process to exit. Its stage-dependent checks, timing, total LUT denominator and any paired long-run qualification remain pending. No accepted baseline, browser or GitHub state changes.
## Terminal result: not promoted

The full-ILA payload-seed1 build completes with 9602 total LUT / 5000 FF / setup WNS -0.042 ns at 151.2 MHz. The 42-data / 33-trigger / 1024-depth mapping is verified, but timing fails. Its worst path is wb_rd[1] through forwarding and ALU carry-select addition to mem_result[25] (11 levels, 2.287 ns logic, 4.010 ns routing), not the original fetch-prediction enable path.

This is 232 more LUT than the qualified local full_redirect_clock151200 system, with no short-run cycle improvement. The candidate is not promoted, no long-run score is assigned, and neither the board baseline nor the local qualified version changes. Evidence: build/ila/payload-seed1/physical-qualification.json and report_timing/pds_soc_top.rtr. Bitstream SHA256: 4B10FD0E9444A08DA2410EFB9FEF196ED671E02036F7FE6D85CA5DF394549F80. Earlier pending/launch descriptions below are historical.
