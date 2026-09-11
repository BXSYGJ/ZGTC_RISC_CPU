# Execution-efficiency screening

Preserve the accepted DC90363D core, UART, GPIO, and 42-data/33-trigger ILA. No candidate is promoted by proxy evidence. At least 157.5 MHz and non-decreasing measured CoreMark/LUT are mandatory gates.

## Index rotation screen

The source-hash-bound historical ten-iteration resolution trace contains 524172 timed conditional branches. All seven alternatives regress from rotation 4 (53871 redirects); the nearest, rotation 6, adds 410 redirects. Three Python tests verify the index formula and original-model state. Do not spend physical implementation runs on these candidates based on this evidence.

## Folded local history

Screen a fourth local-history bit folded into the existing three-bit bank selector. The predictor retains eight two-bit counter banks and 256 tagged entries; it would require one additional history bit per entry and XOR selection logic. This is a generic history transform, not a program-address specialization. Fold zero is a behavior control matching the original three-bit model. Historical resolution-order replay does not model pipeline query/training overlap; a promising result requires actual RTL V0/V1 cycle tests before physical implementation.

## Screening outcome

All seven fourth-history-bit XOR folds regress; the nearest adds 113 conditional redirects. Five alternate two-bit-counter initialization/state-machine policies also regress; the nearest adds 420 redirects. Each screen reproduces all timed baseline conditional predictions, counts all 648458 records, and distinguishes proxy results from physical performance. Formula/state tests pass. These are bounded negative results for one historical performance trace, not proof of global optimality. No RTL candidate was promoted from these screens.

The next actual implementation is `../full_mul_precompute`, which targets independent multiply latency using registered partial products rather than benchmark-specific branch addresses.

