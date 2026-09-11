# Shared FIFO occupancy adder

This isolated candidate starts from DC90363D. Only the occupancy-counter update in `rtl/rv32_fifo.sv` changes: the exact increment/decrement cases use one addend, +1 for push-only and -1 for pop-only. Case matching, simultaneous exchange, hold, reset, depth, width, read/write pointers and memory are preserved.

CPU, UART, GPIO, timer, caches, PLL and constraints remain byte-identical to the baseline. This is not the rejected UART-shift or CPU-comparator-sharing candidate.

## Regression

Run `python test_shared_count.py`.

- 32768 pairwise cycles each at width/depth-bit settings 1/1, 8/2, 8/4 and 32/6: all public outputs compared, including invalid data and X/Z controls.
- 16 resets per configuration, wrapping, filling, draining and full simultaneous exchange.
- Independent queue-model test: 7048 checks, 885 transfers, 130 full exchanges.
- Full peripheral test: 3811 checks and 831 request waits, using this FIFO with unchanged UART/GPIO/timer.
- Six incorrect arithmetic/protocol variants must fail at runtime.
- Exact one-block source delta and byte-identical other RTL/PLL/constraints.

These tests do not replace full CoreMark or board testing.

## Physical qualification

Ordinary run: `build/pds/20260910-153811-5a97d1ba`, 157.5 MHz, placement seed 2, exact accepted V0 firmware (SHA-256 beginning 0E5EAD29).

Full ILA run: `build/ila/20260910-fifo-shared-count-seed2`. The fresh directory contains only captured synthesis inputs before invocation; no historical reports or bitstreams are copied. `audit_ila_mapping.py` verifies all 42 data / 33 trigger / 1024-depth connections and tested RTL hashes. `qualify_full_ila.py` verifies input/output provenance, completion, timing and post-route resources; its unit tests exercise rejected evidence and physical-versus-hardware qualification boundaries.

Accept only with full-system 157.5 MHz timing closure, improved full-system resource efficiency, unchanged execution efficiency and source-bound CoreMark/board validation. No baseline replacement or GitHub push occurs from a simulation or ordinary PDS result.

## Closed under execution-efficiency priority (2026-09-10)

The ordinary PDS run completed with 9135 post-route LUT, 4273 FF and WNS -0.324 ns. Against the matching ordinary baseline (8996 LUT, WNS -0.157 ns), this is worse in both area and timing. Direct synthesis FIFO instances also did not show an area reduction from the shared source expression.

No full-ILA implementation was launched: its directory and audit entrypoints are prepared inputs only, not verified mapping or physical results. This FIFO-only change offers no measured execution-cycle benefit and is not pursued under the revised execution-efficiency objective. The accepted baseline remains unchanged.
