# Experimental native m1 bridge validation (2026-11-01)

Persistent module, TB, runner and interface notes are in
`sim/experiments/npu_m1_bridge/`. Production RTL is unchanged.

The persistent runner was freshly executed:

```text
python sim/experiments/npu_m1_bridge/run.py
NORMAL PASS native m1 bridge transactions=70 weight_words=480 activation_writes=20 activation_reads=20 same_done_r=14 delayed_done_r=20 early_done_r=16
RESULT: PASS native m1 bridge 70 normal transactions plus truncated-read abort explicit failure
ok=True
```

Raw log: `build/sim/npu_m1_bridge_experiment/run.log`.
Simultaneous weight and activation clients keep requests asserted until their
respective completion/acceptance events. Native service latency is randomized.
Tests check command stability, route exclusivity, no native write before
its data is available, exact data readback, no duplicate transaction, and
bounded pending-client waits. Arbitration alternates priority after completed
transactions when both clients are pending. Native done is tested before,
with and after the last upstream read beat. A final abort with an incomplete
read checks explicit failure without fabricated success and a sticky quiet
FAULT state.

Review of production `ddr3_ctrl_axi.v` revealed that its done derives from
IP `axi_rlast`, whereas upstream read valid derives from a FIFO. Therefore
native done can precede final upstream data. The initial bridge that released
ownership immediately on done passed a weaker 70-transaction test but failed
the stronger early-done test at 905 ns (`weight truncated`). That initial PASS
was insufficient for native-controller compatibility; the counterexample is
retained locally at `build/npu_m1_bridge/earlydone_counterexample.log`.

The corrected bridge deasserts the native command after native done but keeps
the read owner until all requested beats have actually transferred. Because
production `rd_valid` is not ready-gated, counting uses `m1_rvalid &&
m1_rd_ready`, not raw valid. Weight done is delayed until native completion
and full upstream delivery have both occurred.

The interface also includes `m1_abort`, `transaction_failed` and sticky
`protocol_error`. An abort enters a quiet FAULT state until reset and does not
report successful weight done or activation data/write acceptance. Real-top
integration must wire controller error/abort evidence; native done alone does
not distinguish a watchdog abort, and tying the abort input low cannot recover
an incomplete FIFO transfer. Exact wiring to existing sticky per-master error
signals and full NPU/controller integration still require validation.

Activation command addresses pass through unchanged, requiring 32-byte
alignment and a 28-bit address. The experiments use base `0x00400000`, not the
existing `0x00200000` spectrum region. Geometry, address whitelist expansion,
rowstore integration, implementation resources, timing and board behavior
are not established by this isolated protocol test.
