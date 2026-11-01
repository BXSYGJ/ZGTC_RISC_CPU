# Original bare core at 155.25 MHz

The selected fixed-boundary CPU passes all 10 slow/fast timing tables at 155.25 MHz. Worst setup slack is +0.176 ns with an actual 0.200 ns uncertainty deduction, satisfying the requested minimum 0.150 ns budget. The reported slack already includes that deduction. SELECTED_BUILD.json binds the exact native timing report, source manifest, physical fixture test, and independent area audit.

The eight frozen CPU files and rv32_bare_core wrapper are unchanged. The DUT includes its native register file and branch predictor; it has no external cache, memory service, peripheral, PLL, or ILA module. Physical distributed RAM uses 312 LUT sites, and the multiplier uses 4 APM blocks.

The full physical fixture uses 4,386 LUTs and 2,775 registers. Exact native hierarchy attribution assigns 3,859 LUTs and 1,543 registers to the core. Following generated constant consumers gives 4,028 core-exclusive LUTs; one shared and two unexported slots yield the conservative core range 4,028–4,031. The fixture uses 355 exclusive LUTs and 1,232 registers. The global sum is 4,028 + 355 + 1 + 2 = 4,386. Use 4,031 as the conservative LUT denominator for external-service efficiency comparisons.

The separate scan fixture controls all 176 non-clock core input bits. An always-capturing 439-bit bank samples every output each core edge. Serial capture loads the previous-edge snapshot. The phase register permits scan shift, activation, and capture once every 2 core edges. External control launches on a falling edge, and the receiver samples the serial output at the second rising edge. Only scan_out has a 2-cycle setup/1-cycle hold exception; internal core paths remain single-cycle. The exact build fixture passed 179 patterns, atomic input update, every serial output bit, snapshot latency, and alternate-edge hold.

Local functional qualification compares the extracted CPU with the original SoC for 2,000,000 CPU edges and 4,000,000 full-port frames, detects an intentional input fault, and reproduces the baseline after rollback. Exact source and parameter hashes join this finite result to the completed unchanged 6,000-iteration source SoC run. That full run used external cached-system services. The release does not claim a new standalone memory-service score. All qualification is local RTL simulation; no board operation is required.

The first seed 2 fixture and its failed timing are retained separately. The selected bounded correction uses SlowScanStaged, seed 1, and physical duplication. No CPU functional source changed.
