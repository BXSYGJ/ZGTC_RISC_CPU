# One-bit recent-branch correlation

This isolated predictor screen changes only rv32_btb.sv versus full_redirect_clock151200. Counter bank capacity, complete SoC RTL, firmware and compilation parameters are preserved. The three-bit variant XORs all local and global history bits; the one-bit variant XORs only the latest global outcome into the oldest local-history position. Neither is a promoted full-ILA image.

V0: 3004793 versus 3004340 cycles (453 more). V1: 3008116 versus 3007840 cycles (276 more). Both CRCs and retired counts match the reference. These ten-iteration results are execution screens, not reportable scores or timing/resource qualification. No current-baseline throughput-floor decision is inferred from them. No execution improvement or measured resource/frequency advantage supports promotion.

Run test_btb.py in WSL for 72 positive parameter configurations and 24 rejected compiled mutations. screen.py and screen.py --validation each refuse to overwrite their respective build/v0 or build/v1 directory. Source/firmware/compiler/output hashes are recorded in each manifest.json. See ../full_redirect_clock151200/CONTROL_EVENT_PROFILE.md for the diagnostic motivation, mutation-coverage correction and complete comparisons. No GitHub or remote-board operation is performed.
