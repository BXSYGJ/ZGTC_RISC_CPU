# WDMA weight-stream handshake experiment (2026-11-01)

Persistent reproduction assets are in `sim/experiments/wdma_handshake/`.
They are experimental module snapshots; production RTL and runner suites are
unchanged. The runner derives temporary hex from tracked weight image bytes.

Actual fresh runs of the persistent assets:

```text
python sim/experiments/wdma_handshake/run.py baseline
weight mismatch layer=0 group=0 tap=1
got=cbc78a9c84208c7fce1dca0cb2c59873
exp=9685d8b9c0dc66942d3b51640f357f7c
ok=False (exit 1, expected reproduction)

python sim/experiments/wdma_handshake/run.py fixed
LAYER PASS 0 groups=7 checks=63
LAYER PASS 1 groups=3 checks=1359
LAYER PASS 3 groups=2 checks=4815
LAYER PASS 5 groups=1 checks=4943
RESULT: PASS WDMA real image randomized backpressure checks=4943
ok=True (exit 0)
```

Raw logs: `build/sim/wdma_handshake_experiment_baseline/run.log` and
`build/sim/wdma_handshake_experiment_fixed/run.log` (ignored build evidence).
The test forces 40 ready-low cycles at each group's first tap, then randomized
ready. All 4943 accepted words are compared to the actual image. Coverage
includes conv1 odd half-beat groups and row rollover, long multiburst groups,
deepest conv4 group, and fc2 8-byte packing. See experiment README for details.

Baseline is build step6, which already layers parameter beat indexing,
channel stride, shift addressing, final partial tap, earlier group-start and
parameter-prime changes over production. Fixed adds only combinational
current-FIFO weight valid/data presentation, removing their registered
assignments. Pointers still advance synchronously on actual acceptance.
The former registered data lagged pointer advancement and could repeat tap 0
when ready resumed after a stall. No repetition or skipped tap was observed
with the fix under this test.

Exact source SHA-256 at validation:

```text
wdma_step6_baseline.v
5AFD689319A1F2B00CF9CF8F005F1EF22C01BB4DBB2B334E4DA7F88E7F7140DB
wdma_fixed.v
2CCBF5B9D337F9D30F7DDD69F1659448AB1B3FA21301BEC6F8C7452DEFA39C1B
```

This is a stream-contract result. Parameter correctness, full NPU golden,
synthesis timing of the new combinational selection path, RAM inference and
board behavior require separate verification.
