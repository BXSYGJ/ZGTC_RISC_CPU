# Idle qualification experiments

These files are isolated experiments, not production RTL. The production memory system and multiply/divide unit are restored to the measured 126 MHz snapshot from build/pds/20260907-010518-97b194c6.

The MMIO-only variant fails timing at both 126 and 135 MHz. The combined MMIO and idle-remainder-clear variant passes 126 MHz but uses 10347 LUT versus 10208 for the measured baseline, has lower timing margin, and still fails 135 MHz. Neither variant was programmed onto a board.

test_mmio_payload.py and test_divider_idle_clear.py explicitly compile these isolated files for reproducible positive and negative controls. Production build scripts only select rtl/ sources. See docs/MMIO_PAYLOAD_QUALIFICATION.md and docs/DIVIDER_IDLE_CLEAR.md for the four implementation snapshots, independent source hashes, and evidence boundaries.
