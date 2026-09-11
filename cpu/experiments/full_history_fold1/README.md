# Folded four-bit local history

September 10, 2026. Isolated from ../full_control_commit. Only rtl/rv32_btb.sv differs among physical sources; GPIO, UART, CPU, PLL and constraints remain unchanged. source-inputs.json records the exact source hashes.

Four history bits map to eight two-bit counter banks by folding the oldest bit into pattern bit 1. This is an unqualified experiment, not a replacement for the complete parent.

Both matched short tests are slower than the parent. Build identifiers are 20260910-214745-739147e5 and 20260910-214757-e33e0da1. No physical timing, area, long-run score or hardware qualification is claimed.

The authoritative paired audit and full comparison are ../full_control_commit/build/history-screen-comparison.json and ../full_control_commit/HISTORY_COMPRESSION_SCREEN.md. Native RTL/model tests and mutation controls pass; original failed test logs, where present, remain preserved.

The next performance investigation focuses on fetch recovery scheduling rather than adding more predictor state. No Chrome or GitHub action was taken.

