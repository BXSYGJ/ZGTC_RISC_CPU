# VexRiscv stages and 153 MHz resource efficiency

Current objective, 24 September 2026: complete tasks 1 and 2 below before any
further R58 frequency experiment. This supersedes the earlier instruction to
stop all future frequency work, but only after these prerequisites are met.

1. Transfer the latest 144 MHz R58 redirect preprocessing to pinned VexRiscv.
   Measure an unchanged baseline, the existing v30 redirect-slot allocation,
   and a new early request stage using the same CoreMark and all 19 Embench
   binaries. Report incremental and cumulative cycle changes. Preserve the
   existing predictor, pipeline configuration, cache fabric and peripherals.
   Check architectural traces, delayed responses, backpressure, reset,
   misalignment, illegal instructions, ECALL, interrupts and MRET before
   benchmarking. Preserve failed trials and hashes. RTL cycle results alone
   are not physical timing or board qualification.
2. Transplant R58's read-only cache valid RAM into isolated derivatives of the
   accepted 153 MHz architecture. Preserve its fetch implementation initially
   to isolate storage changes. Check refill, error, reset and flush behavior,
   then implement both full-ILA and ILA-free images at 153 MHz. Maintain the
   original 0.150 ns setup uncertainty and require all internal timing checks
   to pass. Compare complete-image resources and board CoreMark/LUT against
   the reproduced 9502-LUT accepted image and R58's 0.072277 CoreMark/LUT.
3. Only once both preceding tasks are fully qualified, investigate further
   frequency increases for ILA-free R58. Do not tune an ILA-enabled R58 here.

Use new immutable variant and result directories. Serialize native Windows
PDS jobs. Reuse existing qualified harnesses where their evidence assumptions
still apply, and bind any extension in its own protocol and source inventory.

## Starting evidence

R58 at 144 MHz, seed 3, `packing3_compact0`: 6792 LUT, 3302 FF,
21 DRM, 4 APM, +0.003 ns setup and +0.100 ns hold. Original setup
uncertainty is retained. The narrow margin qualifies this exact image only.

Full-length V0 and V1 RTL have now completed and match all six cold-programmed
board observations. Final reviews:

- `results/coremark-loader-review-20260924T150109Z-83615909`
- `results/selected-coremark-board-review-20260924T150110Z-94a8383d`

V0: 1760010319 cycles, 1649428429 retired, 490.906213 CoreMark,
3.409071 CoreMark/MHz and 0.072277 CoreMark/LUT at configured 144 MHz.
The PLL frequency has not been independently measured.

The existing v30 VexRiscv transfer allocates the redirect PC slot sooner; it
does not yet issue the target bus command in the redirect cycle. Its measured
Embench geometric-mean gain of 0.879866% is an intermediate-stage result.

The accepted 153 MHz source remains
`../cpu/experiments/full_fetch_commit_factored`, with reproduced full-ILA
9502 LUT, 5079 FF and +0.021 ns setup. Its V0 board score is 511.317879
CoreMark. A new area derivative must earn its own timing and correctness
qualification; these accepted numbers must not be copied into a new receipt.
