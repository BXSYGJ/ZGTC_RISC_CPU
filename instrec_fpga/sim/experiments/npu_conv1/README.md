# Full conv1 experiment

Run from `instrec_fpga`: `python sim/experiments/npu_conv1/run.py`.

The real NPU controller, WDMA, WBUF, convolution core and synchronous feature
ROM execute conv1. The DDR weight model returns the tracked 691040-byte weight
image. `feat_u8.bin` is the exact unsigned 64x258 input fixture used during
diagnosis; it is deliberately retained because the legacy similarly named
golden feature NPY is not this fixture. The runner freshly calculates expected
conv1 with `golden_pipeline.conv2d_int8`, then transposes NCHW to the actual
row/group/column/lane output scan. Every output byte is compared.

Validated 2026-11-01: **792576 output bytes exact**, **859229 cycles**.
Evidence: `build/sim/npu_conv1/run.log` (reproducible, ignored build output),
with independent pre-persistence logs `build/sim/npu_conv1_step8/run.log` and
`build/sim/npu_conv1_step9/run.log`.

Candidate changes: per-beat WDMA parameter loading and 16-channel group stride;
synchronous parameter RAM priming; stable WDMA weight handshake; synchronous
WBUF replay lookahead and reload-valid masking; explicit
`x0_ingress_max_row` credit output with feature raster counters in NPU top.
The credit permits input through output row+1, preventing the three-row ring
from being overwritten. Feature issue and its delayed valid are gated together.

These are isolated candidates, not the current synthesis source set. Success
proves conv1 with this fixture and weight model. It does not prove later-layer
activation buffering, native DDR arbitration, timing, resource use or hardware.
