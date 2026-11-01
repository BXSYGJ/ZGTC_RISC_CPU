# NPU interlayer storage review (2026-11-01)

Read-only RTL review; no mainline RTL or PDS input was changed. This is a structural finding, not a new simulation PASS.

## Confirmed blockers

`src/npu/npu_top.v` serializes conv1, pool1, conv2, pool2, conv3, pool3, conv4, pool4. The same conv MAC core cannot scan two layers concurrently. Pool outputs are nevertheless connected immediately to the next conv ingress during the preceding conv scan.

`src/npu/conv_engine.v:349-360` has only three rotating row banks per geometry. Ingress writes row modulo three (`g*_wr_bank`), without a ready signal or ownership check. `g*_row_done` is a completion bitmap, not proof that the row still resides in RAM. Full-frame prefill destroys earlier rows. At `start1`, `start2`, and `start3`, ingress row/column/channel counters and every row_done bit are cleared (`:561`, `:590`, `:619`); the prior pool stream has already finished, so the following scan can then stall on row_ready with no future producer.

| Consumer | Input frame | Bytes per row bank | Three-bank bytes | Whole frame bytes | Rows surviving after full prefill |
|---|---:|---:|---:|---:|---|
| conv1 g0 | 64 x 258 x 1 | 258 | 774 | 16512 | 61, 62, 63 |
| conv2 g1 | 32 x 129 x 48 | 6192 | 18576 | 198144 | 29, 30, 31 |
| conv3 g2 | 16 x 64 x 96 | 6144 | 18432 | 98304 | 13, 14, 15 |
| conv4 g3 | 8 x 32 x 192 | 6144 | 18432 | 49152 | 5, 6, 7 |

The conv1 feature replay also runs continuously for 16512 bytes (`npu_top.v` feat_run), while the conv core takes many cycles per output pixel. Its three-line buffer has the same overwrite risk independently of layer transitions. A replay solution must pace conv1 too.

## Stream order mismatch

`pool_engine.v` explicitly emits `(row, group, column, lane)`, where group and lane identify 16 channels. Its counters advance lane, then column, then group, then row. `conv_engine.v` ingress advances channel, then column, then row and writes `channel * width + column`. Thus pool output is not the expected `(row, column, channel)` order when CIN exceeds 16. This is independent of capacity and start clearing. A cache/replay design must scatter writes using actual group/column/lane coordinates or modify ingress counters to decode the real order. Merely increasing RAM depth cannot repair this mismatch.

## Start/reset timing problems

- Shared pool counters reset on `pool*_start`, which occurs after the producing conv ends. During the next conv's production, the pool can still carry counters from the preceding geometry. Reset must occur at the beginning of each producing conv, before its first output. The subsequent POOL state should only wait for pipeline drain/completion; it must not reset a live/sticky completion.
- `pool4` output is accumulated by GAP during conv4, but `gap_start` occurs after POOL4. In GAP's S_ACC state that pulse clears coordinate counters after all inputs may already have arrived. On later inferences, S_DONE only re-arms at that late pulse, so the next input frame can be discarded. Arm GAP before pool4's first output, and wait for its result completion later.
- FC2 already has a full CIN input vector buffer and consumes FC1 output while in S_X; it is not the three-line overwrite case. Its parameter/start timing remains a separate end-to-end verification item.

## Capacity budget

Use the project design document's 18Kb DRM-equivalent accounting; do not equate a raw 36Kb primitive declaration to one 18Kb count. Exact packing requires synthesis.

- Current mapped baseline: DRM 80.5 / 155, leaving 74.5 equivalents, approximately 171648 raw bytes before packing/port constraints.
- Largest full activation frame alone is 198144 bytes, at least 86 x 18Kb equivalents. It does not fit as an additional buffer.
- Keeping pool1, pool2, pool3 frames simultaneously costs 345600 bytes, at least 150 equivalents.
- Lifetime-aware two-buffer ping-pong can share pool1/pool3 storage, but requires 198144 + 98304 = 296448 bytes, at least 129 equivalents. Adding this to 80.5 exceeds capacity.
- Even replacing all g1..g3 line banks saves only 55440 bytes (about 24 raw equivalents), insufficient to make that two-frame design fit.
- Pool4 is 4 x 16 x 256 = 16384 bytes. It can stream directly into a correctly armed GAP and need not use a full-frame cache.

These are optimistic bit-capacity lower bounds. Memory mode, segmentation, muxing and address widths can only increase costs.

## Recommended minimal serial architecture

Keep the shared conv MAC and small row banks. Store pooled activations in two reserved DDR3 regions, alternating source and destination at layer boundaries. Reserve at least 198144 and 98304 bytes, both 32-byte aligned, outside audio, weights, Mel and diagnostic ranges; actual addresses must be allocated from the authoritative memory map rather than invented here.

1. Pack pool1..pool3 bytes into 256-bit writes with explicit coordinates. A simple linear `(row,group,column,lane)` DDR layout avoids random write scatter; replay decodes this order or transposes one row into the consumer bank.
2. Add activation write command/data outputs to NPU and arbitrate with the existing m1 weight path at transaction boundaries. The current npu_top interface is read-only, so a local RAM patch alone cannot implement DDR spill.
3. Use a small packing FIFO with a proved capacity bound. Pool output currently has no ready; either guarantee enough FIFO depth for the controller's worst bounded response latency, or add backpressure to the conv drain/pool path. Never assume arbitrary DDR stalls are bounded.
4. Before each conv2..conv4 start, reset the selected ingress state, then replay source rows into the three-bank cache only when a bank is free. Initially fill rows 0 and 1; refill row r+2 only after scan output row r has retired and no old window still references that bank. Add explicit row ownership/credits; row_done alone is insufficient.
5. DDR R cannot be backpressured. Issue a read burst only when FIFO/row-bank capacity covers the entire accepted burst. Adapt the existing dummy-write/read contract through ddr3_ctrl_axi rather than duplicating PHY assumptions.
6. Gate conv1 Mel replay with the same row credit scheme. Move pool reset to conv start and GAP arm to conv4 start. Preserve completion pulses until the sequencer's wait state has consumed them.
7. Full-frame writes must finish before reusing/switching a DDR region. Weight reads and activation reads/writes may serialize; performance is secondary to correctness for this delivery.

This is the lowest-risk direction under the existing serial compute and resource budget. Restoring full original interlayer streaming requires concurrently active layer compute or a resumable tile scheduler, plus every boundary's ready/credit protocol; it is a larger architectural change than DDR spill.

## Required evidence before accepting a repair

- One true npu_top simulation with actual feature/weights and no forced done: compare every conv and pool output, natural layer transitions, two consecutive inferences.
- Explicit checks for row-bank overwrite, real pool order, producer-start pool reset, GAP re-arm, and delayed/arbitrarily gapped DDR responses within declared FIFO bounds.
- Separate backpressure/credit tests must fail for the original design and pass for the repair.
- Then compile/synthesize and inspect actual DRM/LUT mapping before launching another PDS route. Current frozen PDS run is unaffected and cannot contain these fixes.