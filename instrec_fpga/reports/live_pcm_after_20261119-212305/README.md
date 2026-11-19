# Superseded capture: diagnostic half-stride error

The board correctly classified all four sources, but these PCM captures are **not valid for exact logit comparison**. The first version of `diagnose_live_pcm.py` used the valid window byte length (264192) as the ping-pong slot stride, instead of 270336. All four captures selected half 1 and consequently prepend 6144 padding bytes and omit the window tail. This explains the small golden logit differences; it is a host diagnostic defect, not evidence of an FPGA arithmetic mismatch.

Retained unchanged for traceability. Corrected, exact comparisons are in `../live_pcm_after_correct_stride_20261119-212636/`. Both physical halves are covered there. The helper now uses `diag_dump.PCM_WIN_STRIDE`; two tests exercise padded physical slots for odd and even window IDs.
