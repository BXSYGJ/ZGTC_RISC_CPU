# Final 153 MHz CPU release

The selected implementation is `experiments/full_fetch_commit_factored`.

Its accepted result is 153 MHz, 511.317879224 CoreMark, 3.341946923 CoreMark/MHz, and 0.05381160590 CoreMark/LUT using 9502 complete-system LUT and 5079 FF. GPIO, UART, caches, and the complete 42-data/33-trigger/1024-sample ILA configuration are retained.

Use `experiments/full_fetch_commit_factored/README.md` for the release description and `scripts/verify_153mhz_handoff.py` for the portable evidence check.
