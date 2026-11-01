# WBUF synchronous-read candidate validation (2026-11-01)

## Result and scope

The build-only `build/npu_full/wbuf_step4.v` candidate passed an independent
Verilator unit simulation with **10,797 accepted tap comparisons** and zero
data mismatches. No duplicate or skipped tap was observed after random stalls.
This is a WBUF behavioral result only; it does not establish full NPU golden
correctness, FPGA timing closure, block-RAM inference, or board behavior.

Mainline `src/npu/wbuf.v` and the simulation runner were not modified by this
experiment. The candidate was not included in the already-running PDS build.

## Preserved candidate repair

Candidate SHA-256 (exact bytes tested):

```text
7789E39AA88E3723343CD6332D7C4F49BB0CA429095CA197B3BC261D9AC7D195
```

The complete candidate change relative to mainline is preserved below so the
repair can be recovered if ignored build artifacts are removed:

```diff
--- a/instrec_fpga/src/npu/wbuf.v
+++ b/instrec_fpga/src/npu/wbuf.v
@@ -71,7 +71,7 @@
     end

     always @(posedge clk) begin
-        rd_data_q <= mem[rd_cnt];
+        rd_data_q <= mem[(state == S_RPY && rd_vld_q && rd_ready) ? ((rd_cnt_p1 >= tap_num) ? 11'd0 : rd_cnt_p1) : rd_cnt];
         rd_vld_q  <= (state == S_RPY);
     end
```

On an accepted replay beat, the synchronous read selects the next pointer
(including wrap) so the following cycle has the next tap. While stalled, it
continues reading the current pointer. The first replay read remains pointer
zero because `rd_vld_q` is not asserted until replay has begun.

## Actual test coverage

Temporary testbench: `build/wbuf_probe/tb_wbuf_probe.sv`.
Temporary invocation: `python build/wbuf_probe/run.py` from `instrec_fpga/`.
Raw compile and simulation log: `build/sim/wbuf_step4_probe/run.log`.
Tool: Windows-native Verilator 5.050 with the existing `sim/run_sim.py` API.

- Active lengths: 1, 9 and 1728 taps, using the default 16 lanes.
- Continuous ready and deterministic random backpressure at each length.
- Multiple complete replay wraps, with every accepted 128-bit word checked.
- Group reload sequence: 1 -> 9 -> 1728 -> 9 -> 1, each with a new data tag.
- Explicit check that `grp_start` masks the old group's replay valid on its
  assertion cycle, including a ready consumer at that boundary.
- Word pattern depends on both group tag and tap index, so stale-group data,
  repeat and skipped indices are distinguishable.
- Random generator: xorshift32 seed `0x178456ab`, shifts left 13, right 17,
  left 5; ready is asserted when the low three bits exceed 2.

Test requests were 40 continuous + 100 random accepts for length 1,
100 continuous + 500 random for length 9, 4000 continuous + 6000 random for
length 1728, then 25 random for a new length-9 group and 25 continuous for a
new length-1 group. The testbench allows a final already-enabled ready cycle
while it exits a consume task; those additional handshakes are also checked,
giving the actual total of 10,797 comparisons.

Preserved simulation result:

```text
RESULT: PASS wbuf step4 checks=10797 continuous/random stall tap_num=1/9/1728 and group reload
- tb_wbuf_probe.sv:57: Verilog $finish
- Verilator: $finish at 166us; walltime 0.009 s
```

Pending before promotion: full NPU golden validation and relevant mainline
regressions. This report preserves the proposed repair, not authorization to
change the frozen in-flight PDS source set.
