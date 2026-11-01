# RV route resource review (2026-11-01)

This is a read-only review of run `build/pds/20261101-130420-0ed52a5d`.
No PDS process was started/stopped and no active RTL input was changed.

## Evidence

- `build.tcl:183`: plain `pnr`, no seed override, explicit timeout or iteration cap.
- `multiseed_summary.csv`: Single Seed; mapped LUT 35840/66600, FF 53845/133200,
  DRM 80.5/155, APM 90/240.
- `pds.stdout.log:30776`: placement Design Utilization 81% (different metric from LUT utilization).
- `pds.stdout.log:29550`: 1383 unique control sets; maximum fanout 1882.
- `pds.stdout.log:31003`: 90057 nets for routing.
- Iteration 140 to 188 decreased from 7660 to 6639 unrouted nets with oscillation.
  This is slow progress, not evidence of a completed or failed route.
- `top_rv_core.v` explicitly overrides CPU ENABLE_M to 0; the child module default
  ENABLE_M=1 does not describe this build. Predictor is disabled too.

## Synthesis primitive counts

Counted declarations matching `GTP_*` inside each module of
`synthesize/top_rv_core_syn.vm`. These are raw synthesis declarations, not
post-map LUT equivalents; repeated module instantiations require expansion
before summing a whole design.

| Module | LUT declarations | DFF declarations | MUX declarations | DRM declarations |
|---|---:|---:|---:|---:|
| wdma | 7149 | 20941 | 2673 | 0 |
| fft2048_sdf | 6107 | 3267 | 0 | 13 |
| conv_engine | 2800 | 4873 | 236 | 21 |
| fc_engine | 2784 | 75 | 1583 | 0 |
| weight_loader | 1618 | 2518 | 257 | 0 |
| rv32_core | 1407 | 1865 | 318 | 0 |

`wdma` has 20480 `GTP_DFF_E` declarations explicitly named `pram`.
Its LUT6 count is 6191; MUX2LUT7/MUX2LUT8 counts are 1870/803.
The memory inference report `synthesize/apm_drm_lutram_utilization.log`
does not list `u_npu/u_wdma/pram` as DRM. Therefore the source comment claiming
one block RAM is not true for this synthesis result.

The source writes 8 independent s32 elements per DDR beat for bias/M and
32 independent byte elements per DDR beat for shift (`wdma.v:225-237`).
One synchronous read and a block_ram attribute cannot make those multiple
write addresses into a physical single-write-port memory.

## Minimal optimization candidate

Only a candidate copy and diff exist in
`build/candidates/wdma_wide_port/{wdma.v,wdma.patch}`. Mainline remains unchanged.

- Bias/M addresses 0..511 map to 64 x 256-bit words: word=pa[8:3], lane=pa[2:0].
  Write word is `{bias_or_M, cfg_idx[7:3]}` with unmodified 256-bit rd_data.
- Shift addresses 512..1023 map to 16 x 256-bit words:
  word=pa[8:5], byte=pa[4:0]; reads zero extend the selected byte.
  Write word is cfg_idx[6:3], enabled only when cfg_idx[7]==0. This preserves
  the original no-destination behavior for writes above the 1024-element array.
- Both memories have one synchronous wide read and one wide write per cycle.
  Lane/bank selection is registered beside the RAM output; pq is selected from
  those registered values. Read latency remains one cycle.
- Coincident read/write returns the old value under nonblocking assignment
  semantics, as before. Reads remain active during reset, but pq is masked
  to zero by an asynchronous-reset valid flag, preserving its external behavior.
- A candidate simulation and synthesis gate are still required. No LUT savings,
  block-RAM inference or timing improvement is claimed until measured.

The candidate deliberately preserves cfg_idx update behavior: it changes on
rd_done, not every rd_valid beat. A burst therefore overwrites the same indexed
word repeatedly in the current source. Fixing this separately would change
functionality and must not be mixed into an equivalence-only memory conversion.

## Follow-up

First compare original/candidate beat-by-beat under concurrent writes, reads,
reset and all parameter address/lane boundaries, then run existing conv1,
npu_chain and weight-loader regressions. A candidate-only synthesis gate must
prove DRM inference and actual resource reduction before adoption.

Historical handoff 20261031 records a narrow routing margin around 53.57% LUT
and repeated failures with seed/parallel/decongestion/duplication changes.
Reducing the demonstrated wdma register/mux structure is a better evidenced
next experiment than blindly changing router parameters. This is a candidate,
not a guarantee of route convergence or a reason to interrupt the active run.
