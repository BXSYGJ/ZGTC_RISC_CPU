# H3_Retained_145125

Selected ILA candidate: `D:\AAAFPGA\ILA_Core_Releases_20261101\H3_Retained_145125\builds\20261101-013613-bbd7e86b`. Status: **internal_timing_passed**.

The requested 145.125 MHz target and 0.150 ns CPU setup uncertainty remain in place. CPU slow-corner setup slack is 0 ns. All CPU and debug clock setup, hold, recovery, removal, and pulse-width checks are recorded in the independent multicorner audit.

Post-route resources: 6456 LUTs, 3024 FFs, 26 DRM units. ILA profile: Lean24.

Frozen RTL, PLL, constraints, and firmware remain unchanged. The copied top changes only the firmware INIT_FILE path. The baseline, modified, and separate rollback copy produce identical UART, counters, retirement trace, and 42-signal capture observations over 2000000 cycles.

The new full 6000-iteration local RTL simulation completed with native exit 0. Its complete UART, CRCs, cycles (1743134699), and retired count (1649428429) match the frozen reference byte for byte.

The waveforms are **LOCAL RTL SIMULATION**. Each of the list, matrix, and state kernel windows contains 1024 recorded rising edges, with the actual EX-PC/ex-fire capture predicate at sample 256. CSV, VCD, PNG, SVG, source hashes, ELF addresses, and render checks are in `waveforms/`. The horizontal axis is CPU edge index. Actual simulator edges are 10000 ps apart; logical UART configuration CLOCK_HZ=3200/BAUD=100 and the FPGA target are separate metadata.

The selected physical core captures 24 data signals and uses 17 trigger signals. The recorded 42-signal local simulation is an explicitly mapped superset when the physical profile is smaller. `SOURCE_TO_SELECTED_BINDING.json` checks all 25 frozen inputs, top-level path normalization, firmware and ELF identity, and every selected capture signal against its original waveform index. Board measurement was not part of this local waveform result.

Evidence: `SELECTED_BUILD.json`, `SOURCE_TO_SELECTED_BINDING.json`, `PHYSICAL_ATTEMPTS.json`, `qualification/VERIFICATION.txt`, `qualification/QUALIFICATION_SUMMARY.json`, `qualification/full_reference/`, and `waveforms/WAVEFORM_MANIFEST.json`.
