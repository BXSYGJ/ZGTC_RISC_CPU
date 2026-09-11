# Shared global history screen

This isolated variant replaces 256 separate three-bit local histories with one shared three-bit history at the current configuration. It retains the eight direction-counter banks per entry and all non-predictor SoC sources. The reduction is 765 declared history state bits, not a measured FF or LUT reduction. No physical implementation is qualified.

The independent predictor reference passes 72 parameter configurations and 20 compiled mutation controls. Complete matched ten-iteration screens preserve CRC and retired counts but use 3049626 / 3041204 cycles versus 3004340 / 3007840: 45286 / 33364 additional cycles. Both are slower; this variant is not selected for physical implementation. Short runs do not establish an official score or prove failure of either long-run baseline floor.

Evidence is under build/v0 and build/v1. The qualified full_redirect_clock151200 project remains unchanged. No GPIO/UART/ILA function is removed from a promoted version, and no remote or GitHub operation occurs.
