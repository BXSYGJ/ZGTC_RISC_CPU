# Original 155.25 MHz local RTL validation

All 25 frozen physical V0 input hashes are preserved. Only the copied top wrapper firmware path is relocated. The core RTL, PLL, constraints, and unchanged 6000-iteration firmware remain byte-identical.

Baseline, modified, and rollback copies produced identical UART bytes, retirement trace hash, 42-bit probe hash, signal counts, and cycle count over 2,000,000 simulated edges. Each run entered list 13 times, matrix 27 times, and state 27 times. The recorded probes use native values at each CPU edge.

Three actual 1024-edge function-entry windows are available in ../waveforms. The trigger is Sample 256 with 256 preceding edges and 767 following edges. CSV and VCD retain simulator timestamps in picoseconds; the configured FPGA clock and accelerated UART fixture parameters are recorded separately.

The separate full 6000-iteration local RTL run passed. The simulator exited 0 and produced byte-identical final UART output, 1,782,669,419 measured cycles, and 1,649,428,429 retired instructions. The exact frozen legacy driver and observer remained unchanged; Original uses Verilator 4.038 and the frozen cycle RTL model.

Physical build candidates are tracked independently by their build manifests and timing reports. Local waveform validity does not depend on post-route timing status.
