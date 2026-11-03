# Fixed-feature NPU probe (B-package numeric localization baseline)

Run `python sim/experiments/npu_probe/run.py` from instrec_fpga.

M0 "localizable baseline" deliverable: deterministic feature vectors
driven through the complete native-controller NPU chain (the exact RTL
set of ../npu_full_native, production src/ untouched), with every layer
output exported as a binary snapshot plus
`reports/npu_probe_baseline_20261104.json`. This is the golden truth
source for board-side three-level injection comparison
(feature / PCM / I2S); the first board-side judge is the per-vector
`logits_int32_rtl` / `probs_q16_rtl`, layer walk-back via the
conv/pool/gap snapshots.

Probe vectors (fixed order, deterministic):

| vec | name              | kind                                   |
|-----|-------------------|----------------------------------------|
| 0   | sine440           | real mel of tests/fixtures/sine_440_full.wav (recomputed via golden_pipeline, cross-checked against reports/golden_ref/sine_440_full) |
| 1   | zeros49           | all-49 anchor (zp_in-domain zero = digital silence) |
| 2   | rand20261104      | PCG64 default_rng(20261104) uint8      |
| 3   | sine440_twolevel  | real mel of tests/fixtures/sine_440_twolevel.wav |

No other-class sample exists in the repo (only sine variants and
silence); recorded as-is per task instruction.

Mechanics: one Verilator build (tb_npu_probe.sv, derived from
tb_npu_full_native.sv with the in-TB golden checks replaced by
full-array collection + `$writememh` dumps), then one process per
vector reusing the executable via `+vec=N +outdir=...`. Golden truth is
scripts/golden_pipeline.py bit-level only (torch carries 21..67 LSB
fbgemm tile noise and is never used).

Snapshot layouts (also in the report JSON): conv/pool dumps are in the
RTL output stream order (row, group, col, lane) exactly matching the
DDR activation replay layout; gap is 256 x int32 LE; fc1/fc2 uint8
containers; probs uint16 Q0.16; feat is (64,258) mel-major uint8.

Validated 2026-11-04: all 4 vectors, every layer element-wise identical
to the golden recompute (max_lsb = 0 on conv1..4, pool1..4, gap, fc1,
fc2, logits, probs for all vectors); sine440 additionally identical to
the committed reports/golden_ref/sine_440_full set. Each inference takes
31,115,245 cycles (data-independent, weight-DMA dominated). Total wall
time ~3.3 min. Evidence: build/sim/npu_probe/run.log and per-vector
directories (gitignored, rebuildable).
