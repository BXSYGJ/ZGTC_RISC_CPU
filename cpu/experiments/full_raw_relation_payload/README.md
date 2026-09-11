# Raw operand-relation payload refresh

## Measured target and exact change

Parent: full_return_stack_link. Its full-ILA seed-1 implementation fails setup by 0.109 ns on the path mem_result[28] -> early comparison -> ID issue control -> raw_pair_relation[0].CE. A second placement still fails by 0.041 ns and uses 106 more LUT, so this candidate targets the identified late enable rather than removing required features or declaring a lower-frequency result qualified.

One CPU substitution moves raw_pair_relation <= operand_relation(forwarded_a,forwarded_b) outside the ex_valid guard. The EX operand registers retain their original guard; the later ID-issue relation assignment retains priority. Reset remains 3'b100. When EX is valid, the relation still tracks the captured EX operand pair. While EX is invalid, extra relation updates are allowed because the next valid instruction receives an overriding ID capture before consumption. Parallel ID and forwarded-EX comparisons are retained: this is not the previously rejected comparator-sharing transformation with a late mux before the comparison.

CPU SHA256: A84C842258853FFB395533488909C0D41E6DACFCEBA4A88C384B6DAE6E8893CA. BTB SHA256 remains 74DFB242332EF849015DF301B2BE01A87D32EC7F1811A658F85EA82CBE79305E. change-receipt.json reconstructs the exact source. The two-entry return stack with link reuse, GPIO, UART, caches, clock and constraints are retained. Full 42-data / 33-trigger / 1024-depth ILA remains mandatory for acceptance.

## Completed tests

- Source-extracted sequential comparison passes 10000 cycles, including 6649 live comparisons, 3373 held-EX observations, 848 actual invalid-slot differences, 160 flushes, periodic resets and four-state operand data. Three compiled capture/priority faults fail as expected. This is bounded validation, not formal equivalence over all reachable CPU states.
- The inherited five-depth predictor checks, eight predictor fault rejections, 32768 hint/commit checks and four hint/commit fault rejections pass.
- Eight core/cache tests pass independent ISA trace and final-memory comparisons. The source-bound baseline benches additionally assert live raw_pair_relation equals operand_relation(ex_operand_a,ex_operand_b) at settled clock phases, while retaining their link-value and original functional checks.
- Both full short CoreMark UART logs equal the link-reuse parent's logs byte-for-byte: V0 3000415 cycles and V1 3001205. Retired counts, CRCs and profiling counters match. No new execution-efficiency gain is claimed for this timing-oriented transformation.

The first predictor-test invocation omitted the copied return_stack_tb.sv; its missing-file compile failures remain in build/test_return_stack.py.log. The unchanged required bench was added and all tests then passed in the .complete.log outputs. No RTL assertion or compiler-warning policy was weakened.

## Physical implementation and independent ISA evidence

Ordinary run 20260911-041355-3d1b7a0e completed successfully: configured 151.2 MHz, 9058 post-route LUT, 4363 FF, setup WNS +0.020 ns. Its bitstream SHA256 is FC94877CA2E3C2FC84914568B98EF7B74B8629A9E34C395D7C0DFAD176053FF5. This ordinary resource count is not the required complete-ILA resource denominator.

The source-bound synthesis comparison proves all three raw_pair_relation register clock enables are actually removed: bits 0/1 change from GTP_DFF_CE to GTP_DFF_C, and bit 2 from GTP_DFF_PE to GTP_DFF_P. Reset initialization, reset/clock connections and output nets match. The inclusive core remains 3950 synthesis LUT / 1749 FF / 1165 carry LUT; predictor remains 786 / 322 / 8. These nested synthesis counts must not be added or substituted for post-route system resources. Seven parser/actual-netlist tests pass, including rejection of missing or duplicate registers, an unchanged enabled design and an altered clock. See build/synthesis-comparison.json.

Actual native Inserter enumeration identifies IF/ID/EX/MEM pipeline-valid registers under board/soc/core. The remapped full-ILA image passes source/firmware binding, native register-driver checks and actual Inserter output checks for 42 data / 33 trigger / 1024 depth. Sixteen full-ILA auditor tests pass.

Full-ILA placement raw-relation-seed1 completes but FAILS setup: 9458 total LUT, 5089 FF, WNS -0.066 ns, 11 failing slow-setup endpoints and TNS -0.200 ns. Bitstream SHA256: E6A7AF8B248A33362F359E754F2D047BB2DAA8586F8119D8FC367C1C8F211E0C. It is not qualified and does not replace either accepted baseline. The limiting path now runs from data-cache request_address[5] through tag RAM/hit detection, load-address bypass and read-index comparison to synchronous_writable.forward_way1. It has eight logic levels, 2.090 ns logic and 4.210 ns routing. Removing the earlier relation enable did not close the complete system.

The bounded alternative placement raw-relation-seed2 also completes and FAILS: 9509 total LUT, 5082 FF, WNS -0.092 ns. Bitstream SHA256: 4CE26B645684B753ADDE442ED1731278AE310C904260BFF10B17E4E306297A02. This is 51 more LUT and 0.026 ns worse setup slack than seed 1. Its limiting path runs from mem_result[26] to next_pc[21].CE (11 logic levels, 2.095 ns logic and 4.112 ns routing). Both execution handles are terminal. No further seed sweep is started; full_cache_collision_factored instead tests the earlier collision factoring against the current core and current cache behavior. Neither failed image is promoted.

The exact modified core now independently passes pinned riscv-tests revision 2ebecad997fa58cd9e5724340ba75aa4b59bd1d0: 41 RV32UI tests across four configurations (164 runs), eight RV32UM tests across four configurations (32 runs), and four expected rejection controls per suite. These are fresh candidate-specific runs, not inherited parent evidence. The separate hash/raw-log/Cartesian-coverage audit and four audit tests pass. Invocation SHA256: B33255B0085E9DA1734605910A1D74C7C4A33B393D8738D91CB751E715FB6C14. External cache set bits are 1/4; production geometry is separately covered by the existing core/cache tests. ma_data explicitly expects a precise trap, not transparent misaligned access. This is not complete ISA certification.

Paired long-run scores, timing-qualified complete-ILA images, candidate application integration and remaining board/electrical acceptance are not complete. The SCBV warning remains unresolved; no board configuration voltage is guessed. No new three-metric result, board validation, baseline replacement, browser access or GitHub publication is claimed.
