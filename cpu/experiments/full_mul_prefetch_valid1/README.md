# Guarded raw multiplier-prefetch operands

## Motivation and exact change

The full_return_payload1 full-ILA failure exposes a register_valid -> ID operand mask -> APM input path with 4.286 ns routing, including a 1.845 ns final APM route. This candidate instead starts from full_return_stack1, without the rejected prediction-payload capture change. Earlier regfile_valid_fanout/storage/reset sources were inspected: their validity masking remains on the same general ID operand path. No fanout hint, reset contract or architectural zero behavior is weakened.

CPU SHA256: 0F9EFD4A6C17C6C7A6933AD0615CEC1089CEB79B916C6029AC1E253C10363001. BTB remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. The four exact substitutions are recorded with the complete qualified-parent ancestry in change-receipt.json. GPIO, UART, cache geometry, RV32IM/machine-mode behavior and the required full ILA remain in scope.

The speculative multiplier input now selects WB-forwarded data or raw register-file data, without the register-valid zero mask. The one-bit precomputed marker additionally requires both source indices to be nonzero and both values to be initialized or provided by same-cycle WB forwarding. Zero-register and uninitialized-register multiplies fall back to normal EX operands, which retain the original zero masks and forwarding. Initialized registers containing zero remain eligible. Existing EX/MEM dependency, idle/ready, instruction-type and one-cycle marker-expiry guards remain intact. This changes speculative work eligibility, not architectural result semantics; fallback latency may differ on those excluded operands.

## Functional evidence

Five exact-delta tests pass. Source-extracted operand/gate logic passes 16384 combinations covering both operand indices, same-source cases, WB matches, validity and x0, plus unknown speculative data. Six compiled gate/data faults are rejected. Four actual-core configurations retire seven expected products, including x0, two uninitialized operands, valid zero and dependencies; each observes two successful precomputations and five fallback/dependency cases. Four whole-core faults are rejected by unsafe-operand or incorrect-retirement checks, not watchdog expiry.

Eight existing delayed-response/predictor configurations pass stalled/dependent multiply checks; a retained-marker fault is rejected. Five return-stack depths each pass 4123 vectors, eight predictor faults are rejected, and 32768 commit/hint combinations reject four faults. Eight core/cache executions independently match instruction traces and final memory. These are bounded tests, not exhaustive architectural proof.

The fifteen-method source-bound safety manifest is build/safety/manifest.json, SHA256 CDEA93E264E794374609556F1F492D30BFBE754E951C83BCC948CC93072F9340. It captures current tests, assembly, benches, qualified inputs and raw logs, including the real RV32 compiler identity. Six safety-audit tests pass. The core/cache manifest SHA256 is 623265079CCEFCB3D788BB1B504F676635232109F93CD0EB699093F9285FF091.

Both ten-iteration CoreMark runs retain the one-entry parent results: V0 3000565 cycles / CRC fcaf, V1 3001255 / c64e. There is no measured new short-run execution gain or loss. Long-run performance and complete-system resource efficiency are not qualified.

## Physical status

All twenty physical inputs are staged after regression and safety checks. Ordinary PDS 20260911-055209-ba24d059 completes with 9069 LUT / 4325 FF and WNS -0.010 ns at configured 151.2 MHz. It fails timing and does not supply the complete-system resource denominator. Firmware remains V0 6000 iterations, SHA256 3A82C84E665E212C8BC8CF492CD169D7A579BF20146F810FA104F51EAE61287B.

Native discovery finds all four IF/ID/EX/MEM-valid nets at board/soc/core/pipeline_valid[0:3], unlike the one-entry parent MEM alias. Actual Inserter verification preserves all 42 data / 33 trigger channels and 1024 samples; twenty-one source/mapping/evidence audit tests pass. The full-ILA mul-prefetch1-seed1 job is terminal: 9522 total LUT / 5055 FF, WNS -0.140 ns, eight failing slow-setup endpoints and TNS -0.371 ns. It is rejected, not a qualified score version. Bitstream SHA256: 1236DC2A621F44E3EAF72DF274A00EE3B725CB7E8717EBA1905AF8DAA7793880. Netlist SHA256: BAFDD7DD3F280DD27BD4269F1B47D8B5664B5BC14D75B953AC6718BB0015F573.

The worst path is mem_result[19] -> early branch/control logic -> id_instruction[23].CE: ten logic levels, 1.802 ns logic and 4.478 ns routing. A second failing path reaches raw_pair_relation[0] from id_instruction[16]. The earlier multiplier-input path is not the top reported path in this placement, but no whole-design timing pass follows. Decode payload lifetime is a distinct next structural target; do not blindly repeat this seed or assign a long-run score.

Independent current-source external ISA validation passes 196 RV32UI/RV32UM executions and eight expected rejection controls. Its source/raw-log/coverage audit and four audit tests pass. Invocation SHA256: 38CD48643324FFE22B4B7C965E2122B7570360EB07C038612DC6F04F8614263E. This is bounded external test coverage, not complete ISA certification; the precise-misalignment-trap exclusion and four tested predictor/cache configurations remain explicit.

The supplied topic PDF pages 10-11 were re-read: all five non-AI core/cache/control tasks, a concrete application, the three performance dimensions, at least ten-second CoreMark runs and the ILA-based pipeline analysis report remain in scope. Short-run equality and ordinary synthesis do not replace those deliverables.

No baseline replacement, remote-board test or GitHub publication occurs. Native full-system timing/area, matching long runs, current application and complete local/electrical acceptance remain prerequisites for promotion and eventual remote verification.
