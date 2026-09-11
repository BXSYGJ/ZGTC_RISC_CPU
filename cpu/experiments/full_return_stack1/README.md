# One-entry return-stack tradeoff

## Terminal physical and external ISA results

Ordinary run 20260911-050617-3125c6c4 completes with 9156 LUT / 4326 FF and WNS +0.090 ns at 151.2 MHz. However, the full-ILA return-stack1-seed1 run completes with 9429 LUT / 5026 FF and WNS -0.161 ns, 32 failing setup endpoints and TNS -2.286 ns. This candidate is not promoted. Full bitstream SHA256: 910693592F3B6F3B91E564C31362FA9957EA2B0471A5E5B51FE57279D8DE6CA8. The actual limiting path is wb_data[19] through the early forwarded branch comparison and frontend control to fetch_prediction[4].CE: ten logic levels, 2.216 ns logic and 4.042 ns routing. The ordinary LUT denominator must not replace the complete-system denominator.

Native Inserter mapping verifies all 42 data / 33 trigger channels and depth 1024. Unlike the two-entry parent, MEM-valid is the native parent alias board/soc/unused_pipeline_valid[3]; IF/ID/EX are core-local. The exact CPU output-port connection and register drivers are checked. Twenty-one source/firmware/mapping audit tests pass. Neither aliases nor channels are guessed from the preceding candidate.

The current core/predictor independently pass 196 pinned external RV32UI/RV32UM runs and eight expected rejection controls, plus the source/raw-output/coverage audit and four audit tests. Invocation SHA256: CE68CC248900D074D385384E76482CDB8AAD6D689BF682555F51DB313E528FE2. RV32UI contributes 164 executions, RV32UM 32; production cache geometry remains covered separately by core/cache tests. The ma_data test is an expected precise-trap rejection, not transparent misaligned-access support. This is not complete ISA certification.

No long-run score is launched for this timing-failed version. A distinct follow-up may reuse the already tested prediction-payload capture transformation against the now-measured fetch_prediction.CE path; previous failure of that transformation in a different core context is retained, not relabeled. The latest locally paired benchmark remains full_redirect_clock151200; the board baseline remains DC90363D. SCBV and electrical closure remain open.

## Exact change and reason

This isolated candidate changes only .RETURN_STACK_DEPTH(2) to .RETURN_STACK_DEPTH(1) relative to full_raw_relation_payload. It retains link-value reuse, unconditional invalid-slot relation refresh, the complete RV32IM system, GPIO, UART and all required ILA functions. The failed cache-collision factoring is not included: cache SHA256 remains 984B45FECD7D5AFF9410638DD0234649F2BCB99198EC2933C761B7D6FD5C4343.

CPU SHA256: C8D8002ADA85F260814640F94419FD1FAAF5450B4A38D2481B2EE560DA605D30. Predictor SHA256 remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. change-receipt.json records both the immediate-parent one-line delta and the full qualified-parent reconstruction chain. No predictor entry, UART/GPIO function, cache capacity or ILA channel is removed.

The source-bound committed-order replay in ../full_cache_collision_factored/build/return-depth-tradeoff.json finds 13443 correct return targets / 292 underflows at depth 1, versus 13633 / 102 at depth 2, out of 13735 return hints. Both depths predict all 640 and 300 committed targets at the two largest return-misprediction hotspots. Seven replay tests pass. This replay omits speculative timing, update lag and BTB conflicts; it does not establish saved cycles or physical resource savings.

## Completed validation

Four exact-delta tests pass, including rejection of the wrong depth, unrelated core changes and predictor changes. The predictor suite passes 4123 vectors at each of depths 0/1/2/4/8 and rejects eight compiled faults. Source-extracted commit/hint validation passes 32768 combinations and rejects four faulty conditions. Eight current core/cache runs pass independent instruction-trace and final-memory checks; unchanged parent benches retain committed-link and live operand-relation assertions.

The initial inherited provenance test expected a files reconstruction chain that the first immediate-parent receipt omitted. That metadata failure is preserved in build/test_return_stack.py.log. The receipt now also includes the full qualified-parent chain; all original assertions pass in the .complete.log outputs. No RTL or runtime check was weakened to fix the receipt format.

| Ten-iteration RTL run | Qualified parent cycles | Two-entry raw parent cycles | One-entry cycles |
|---|---:|---:|---:|
| V0 | 3004340 | 3000415 | 3000565 |
| V1 | 3007840 | 3001205 | 3001255 |

Both runs retain the expected retired counts and CRCs fcaf / c64e. The one-entry version costs 150 / 50 cycles versus the two-entry parent, while saving 3775 / 6585 versus the qualified no-RAS parent. These are short RTL screens, not ten-second CoreMark scores. No resource-efficiency claim follows until the complete post-route system and matching long runs are measured.

## Physical status

All twenty physical inputs are staged after source/delta and eight-run regression verification. The new CPU/predictor are the only differences from the qualified source inventory. The wrapper keeps 151200000 Hz and uses the same V0 6000-iteration firmware; all cache, M-extension, predictor and overlap settings are preserved. Staging explicitly records return_stack_depth=1 and the source-selector/delta hashes.

The earlier ordinary implementation launch is now terminal, as is the full-ILA follow-up. See the terminal results above. Existing failed timing evidence is preserved; no automatic restart or baseline replacement follows.

Both baseline floors and all five non-AI tasks remain active. No accepted-baseline replacement, board validation, SCBV/electrical closure, browser operation or GitHub publication is claimed.
