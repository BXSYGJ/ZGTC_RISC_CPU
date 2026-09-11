# Full UART RX shift preservation candidate

This candidate starts from the DC90363D baseline and changes only UART RX storage:
1. Replace indexed bit writes with the equivalent LSB-first shift operation.
2. Apply `syn_keep=1` to the eight-bit RX shift register.

CPU, GPIO, FIFO, timer, cache capacities, instruction set and configured frequency are unchanged. The preservation attribute is an implementation request, not proof of timing recovery.

Run `python test_uart_shift.py` to check both exact permitted edits, byte equality of other RTL, cycle-level UART outputs, all byte values, framing/overrun/reset cases, peripheral integration, and the wrong-shift negative control. These UART/peripheral benches do not execute the CPU or constitute a full CoreMark run.

## Physical qualification

Ordinary synthesis-input build: `build/pds/20260910-140613-ac49d81d`, seed 3, 157.5 MHz, exact baseline performance firmware. Result: 8859 post-route LUT, 4275 FF, WNS -0.224 ns; timing fails. This ordinary build has no ILA and must not be compared directly with the complete 9374-LUT baseline.

Full-ILA run: `build/ila/20260910-uart-shift-keep-seed3`. Qualification requires actual Inserter confirmation of 42 data / 33 trigger / 1024 depth, source hashes, nonnegative timing at 157.5 MHz, and fewer than 9374 complete-system post-route LUTs. No older logs or generated bitstreams are copied into this run.

Hardware CoreMark, validation firmware, GPIO and ILA checks remain required before promotion. No scores are inherited. The accepted baseline is unchanged and no GitHub push is performed.

## Terminal full-ILA result (2026-09-10)

The full-ILA run completed with PDS exit 0, but the physical acceptance gate correctly exited 2:

- 9370 post-route LUT (7132 CLMA + 2238 CLMS), 5014 FF.
- WNS -0.293 ns at configured 157.5 MHz; timing constraints violated.
- 42 data / 33 trigger / 1024 depth verified against this synthesized source.
- Exact source and generated-output hashes are in `build/ila/20260910-uart-shift-keep-seed3/physical-qualification.json`.
- Five complete candidate regression methods pass, including the corrected two-edit source guard; seven qualification-gate tests and ten shared report-parser tests pass.

The worst reported setup path runs from `id_instruction[24]` to `raw_pair_relation[1]`: 10 logic levels, 2.120 ns logic plus 4.140 ns routing. This is not evidence that preserving UART storage fixes the CPU timing bottleneck.

Only UART differs among the 20 captured physical source inputs relative to the original ordinary baseline; generated top-level parameters and firmware match. That comparison is recorded separately in `build/baseline-source-comparison.json`.

This variant is not promoted, programmed, or credited with any CoreMark score. The 8859-LUT ordinary result excludes ILA; the complete comparison is 9370 versus 9374 LUT with failing timing. Stop this UART preservation branch rather than treating a four-LUT reduction as success.
