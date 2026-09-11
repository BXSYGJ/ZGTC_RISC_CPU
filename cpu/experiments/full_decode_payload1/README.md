# Decode payload capture candidate

## Status

Candidate `full_decode_payload1` is not a qualified replacement. Ordinary PDS run `20260911-061640-1c2a196a` finishes at 151.2 MHz with 9068 LUT, 4362 FF and setup WNS -0.260 ns. Its worst path is EX instruction bit 17 through source selection and ALU addition to MEM result bit 31; nine logic levels contribute 2.202 ns and routing 4.306 ns. Ordinary timing fails.

Full-system implementation `build/ila/decode-payload1-seed1` finishes with 9566 total LUT, 5048 FF and setup WNS -0.041 ns at 151.2 MHz. Two setup endpoints fail, with TNS -0.057 ns. The worst path is register_valid[2] through ID operand masking and comparison into raw_pair_relation[0], ten logic levels with 2.052 ns logic and 3.984 ns routing. The other failure is MEM instruction bit 10 through execution data into MEM result bit 22 (-0.016 ns). The candidate is rejected, not promoted. Bitstream SHA256: DC63DC0FBE7F62A7D4CE99421F24A675BAA556F8BFA25887841066801999536D.

Native Inserter discovery confirms all four pipeline-valid nets are core-local, with matching register-Q drivers. Actual Inserter verification and 21 positive/negative audit tests preserve all 42 data channels, 33 trigger channels and 1024 samples. Mapping success does not override the timing rejection. Ordinary resources are not used for resource efficiency.

## Change and scope

Immediate parent: `full_mul_prefetch_valid1`. Exactly two recorded substitutions separate ID payload capture from the late IF-to-ID valid-control condition. Payload loads when ID is empty, EX is empty or EX consumes; IF/ID valid control, flushing, reset and barriers retain their original priority. The existing one-entry return stack, raw relation refresh, guarded multiplier prefetch, GPIO and UART are retained. This is a timing/resource optimization of the parent, not an additional execution-cycle improvement.

CPU SHA256: `A5FBA551C3D6FFA7924E396F44F458D34008E0D89898F519A74F16EEC8E7C45D`. BTB SHA256: `74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E`. `change-receipt.json` records the exact delta and qualified-baseline ancestry. The source selector retains the older raw-relation observer directory solely for trace benches; it is not the immediate RTL parent.

## Validation

- Nineteen source-bound safety methods pass in `build/safety-complete`. Four predictor/overlap differential modes each run 6000 cycles and include IRQ, early redirects, held ID payload, delayed responses, errors, flushes and barriers. Five compiled decode faults are rejected. Four directed redirect modes each pass 35 cases and 444 checks.
- Non-overlap coverage: 34565 checks, 485 additional dead-payload updates, 388 flushes/barriers, 303 held responses, 388 IRQ cycles, 163 early redirects and 52 held-ID cycles. Overlap: 35734 checks, 906 extra updates, 383 held responses, 911 overlaps, 388 IRQ cycles, 177 redirects and 160 held-ID cycles. This bounded test uses synthetic controls and is not formal equivalence.
- Guarded multiplier, return-stack and commit tests remain bound to the current RTL, including operand availability, x0/uninitialized fallback, delayed dependencies and injected faults.
- Eight core/cache trace and final-memory comparisons pass. Six safety-auditor tests pass.
- Both ten-iteration CoreMark UART logs are byte-identical to the immediate parent: V0 3000565 cycles / 2748941 retired / CRC fcaf; V1 3001255 / 2749614 / c64e. No long-run score is extrapolated.
- Pinned external ISA tests pass: 164 RV32UI plus 32 RV32UM runs, eight expected rejection controls and four auditor tests. Invocation SHA256 `8B0377A03A6CB1C564AC36AF3EFE075DC66464B31A716853643EFC6D293099F5`. This is bounded independent coverage, not complete ISA certification.

## Preserved failed evidence

An initial source-delta test exposed an incorrectly substituted parent path; the failed log is preserved. The first differential test then exposed procedural force expressions evaluated only once by Icarus. Continuous wires now drive the forced signals; coverage requires real IRQ, redirect and held-ID activity, and compiler diagnostics reject that warning. The original failed `build/safety/manifest.json` and diagnostic log remain untouched. The corrected successful evidence lives separately in `build/safety-complete`, and assertions were not weakened.

## Acceptance boundary

The locally qualified `full_redirect_clock151200` and board-tested DC90363D baselines remain unchanged. No long benchmark, board score, electrical acceptance, or maximum-frequency claim is made for this candidate. Remote access and GitHub synchronization are not performed.
