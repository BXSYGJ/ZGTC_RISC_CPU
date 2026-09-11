# Two-entry committed return-stack candidate

## Terminal full-ILA result: not promoted

The source-bound return-stack2-seed1 build completes with 9669 total LUT / 5076 FF and setup WNS -0.205 ns at 151.2 MHz. Its actual native mapping retains all 42 data / 33 trigger channels and 1024-sample depth. All twelve physical-input, firmware, native-channel and pipeline-alias tests pass, but timing fails. The bitstream SHA256 is 584DCEC0EAFF5EB6FFA13C52019731C0325F6E395480DFD1088A645043D1C7E5. The candidate is not promoted and receives no long-run score.

The ordinary run reports 9211 LUT / 4366 FF / WNS -0.324 ns. Its worst path is wb_data[29] through early branch comparison and id_fire_without_irq to compare_next_a, ending at N393.lt_1. The full-ILA worst path differs: wb_rd[0] through forwarding selection and the ALU to mem_result[6], eight levels with 1.901 ns logic and 4.467 ns routing. Removing the new stack adder is an area hypothesis, not a demonstrated fix for either worst path.

The synthesis hierarchy reports predictor LUT 757 -> 815, FF 256 -> 322 and LUT-carry count 6 -> 35 relative to the qualified parent. These are synthesis hierarchy counts, not a second post-route resource denominator. The explicit stack update_pc+4 adder motivates ../full_return_stack_link, which reuses the core's existing committed link value while preserving two entries and all stack behavior. Earlier pending statements below are historical.

## Scope and motivation

Parent: full_redirect_clock151200, not the rejected fetch-prediction-payload variant. Only rv32_core.sv and rv32_btb.sv change. The three-bit local-history predictor, cache geometry, GPIO, UART, clock and constraints remain intact. The 42-data / 33-trigger / 1024-depth ILA is still required for physical acceptance; no new full-ILA result is available yet.

The source-bound return_stack_profile replay finds 13735 returns in 2748929 retired instructions. A per-PC last-target model sees 1620 target changes. A two-entry stack supplies 13633 correct targets, no wrong targets and 102 underflows in that committed-order model. This is not a fetch-time prediction measurement or an estimate of saved cycles. It motivates the real RTL experiment instead of another direction-counter sweep.

## Implementation

Each trained BTB entry records whether its instruction carries a return hint. A matching nonconditional return entry uses the stack top when available; empty stacks fall back to the ordinary BTB target. Entry validity and full existing tag checks still apply. Two full-width addresses and a bounded count support push, pop, pop-then-push, overflow and underflow. Reset and predictor invalidation clear the count, so uninitialized address storage cannot be selected.

The core decodes x1/x5 call/return hints from the MEM instruction. Stack changes occur only on mem_fire && !mem_fault && mem_branch. This is deliberately separate from the existing level-sensitive BTB training enable: a stalled MEM instruction must not repeatedly push or pop. Wrong predictions retain the existing architectural redirect/flush recovery. This is a committed stack, not a speculative stack with rollback, so update lag remains a possible performance limitation.

Exact edits and parent/current hashes are in change-receipt.json. Current CPU SHA256: E1F37D3DAA7852B00A8E6AA916500046A6E005E6C6E96F3DA1400B53BE83D343. Current BTB SHA256: DC54C0978A9BBE40905CB97081092D1B30313AB7F94B892036358B02E209AD57.

## Completed local verification

- test_return_stack.py passes depths 0, 1, 2, 4 and 8 with 4123 vectors each. Disabled-stack target behavior and all hit/direction outputs are compared with the qualified parent. Eight compiled faults are rejected; their expected FATAL messages are part of the passing log.
- test_commit_gate.py checks 32768 source-extracted opcode/register/commit combinations, including stalled instructions, faults, nonbranches, alternate link registers and coroutine hints. Four faulty hint/commit conditions are rejected. This verifies the extracted logic and actual stack-port expressions, not a full formal proof.
- run_regressions.py --attempt depthslice passes six core runs and two cached-core runs, with independent ISA trace and final-memory comparisons. Both predictor modes retain traps, timer interrupt handling and zero/positive/negative load-address-bypass coverage. Source, executable, trace, memory, firmware and tool-command records are preserved in build/core-regressions-depthslice.
- Both strict-Verilator ten-iteration CoreMark screens preserve retired counts and CRCs. V0: 3000415 cycles versus 3004340, saving 3925 (throughput ratio 1.0013081523722551). V1: 3001205 versus 3007840, saving 6635 (ratio 1.0022107786705674). See build/v0-depthslice and build/v1-depthslice. These short tests do not establish a reportable long-run score.

## Physical implementation status

The generated build/physical-project-complete-depthslice captures twenty complete physical inputs, with exactly the CPU and BTB changed. Ordinary PDS run 20260911-033657-f616c653 is started at 151200000 Hz, placement seed 1, using the same V0 6000-iteration firmware as the qualified parent. PID 91708 is confirmed alive in native synthesis after the parser fix. Final ordinary timing/resources are pending; ordinary resources do not include ILA and must not be used as the full-system denominator.

The initial run 20260911-033350-a0abf706 stops during parsing: this PDS version rejects the sized cast COUNT_BITS'(RETURN_STACK_DEPTH). Replacing it with RETURN_STACK_DEPTH[COUNT_BITS-1:0] passes all repeated predictor, CoreMark and core/cache tests before the new isolated staging/run is created. Initial sources/logs remain preserved. No tool-warning suppression or change to hardware behavior is claimed.

Two regression setup failures are retained: the first used a 64 KiB helper on a 16 KiB selftest; the second accidentally used the older root bench that forbids load-address forwarding. The final runner validates the actual 16 KiB format and uses the qualified parent's matching bench, firmware and reference checker. No coverage assertion was weakened to make the candidate pass.

## Remaining gates

Ordinary PDS completion, source-bound native 42/33/1024 ILA mapping and full implementation, paired 6000-iteration execution, application integration, and outstanding board/electrical acceptance are not complete for this candidate. Full-system CoreMark and CoreMark/LUT must meet the governing floors. No long score, resource saving, frequency improvement or new hardware result is assigned. The qualified local version and DC90363D board baseline remain unchanged. No browser or GitHub operation occurs.
