# Parallel forwarding alternatives

Both cores are isolated from the production RTL and use the qualified MMIO I9 baseline, not the rejected collision-forwarding cache.

- rv32_core_mask.sv and mask.json: mutually exclusive parallel EX/WB/MEM selection.
- rv32_core_raw_word.sv and raw_word.json: additional aligned raw-word response bypass.
- scripts/test_forward_parallel.py:65792 cases per source/bubble,12 compiled mutations and inherited poisoned-response controls.

Both135 MHz seed1 implementations fail timing. Do not promote them or combine their LUTs with previous long-run counters. See docs/FORWARD_PARALLEL.md for source identities, scope and audit artifacts.
