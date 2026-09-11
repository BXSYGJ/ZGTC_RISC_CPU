# Committed return-stack replay

This source-bound analysis reuses the qualified full_redirect_clock151200 retirement trace and separately verified control-event trace. Run replay.py in WSL because the original command/source paths are WSL paths. The existing control audit verifies source snapshots, firmware, executable, output hashes, UART equality and timed-cycle boundaries before this replay runs.

The 2748929 retired instructions include 13735 resolved return hints. A cold, unbounded per-PC last-target model records 14 cold targets, 1620 target changes and 12101 repeated targets. Stack-depth results are:

| Depth | Correct predicted targets | Wrong targets | Underflows | Overflows |
| --- | ---: | ---: | ---: | ---: |
| 2 | 13633 | 0 | 102 | 101 |
| 4 | 13723 | 0 | 12 | 11 |
| 8 | 13734 | 0 | 1 | 0 |
| 16 | 13734 | 0 | 1 | 0 |

Maximum observed occupancy is six. The leading short-run return hotspots include 0x573c (640 actual MEM flushes) and 0x5268 (290). The report retains per-PC measured flush counts separately from replay predictions. Neither can be converted directly into saved pipeline cycles.

This is a cold committed-order replay, not a speculative fetch model. It omits BTB conflict effects, pipeline update lag and rollback. The final instruction is never assigned an invented successor. There is no modeled interrupt recovery; the source audit requires zero interrupt-pending cycles in the measured interval.

Seven test_replay.py methods pass, including all 1024 JALR source/destination combinations, both link registers, nested calls, overflow/underflow, coroutine pop-then-push, wrong targets, final-record handling and invalid input. Initial zero-counter serialization errors and an attempted Windows re-audit are retained in build/tests.log and build/replay.log. The latter correctly fails the WSL compile-command binding; build/replay-wsl.log is the successful source-bound run. Evidence is build/return-stack-replay.json. The two-entry real-RTL candidate is ../full_return_stack2; its measured short-run cycles, not this replay, determine its execution screen.
