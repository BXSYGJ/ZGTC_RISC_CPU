# RV32IMC implementation and qualification

## Current status

The C extension is implemented and qualified in the complete no-ILA processor system. **The current RTL passes the original 153 MHz timing constraints, full CoreMark, functional regressions and hardware validation.** Qualification completed on 2026-10-01 in Asia/Shanghai; result directory timestamps use UTC.

The hardware-validated 9,600-baud V0 and V1 images have +0.090 ns setup slack and +0.100 ns minimum hold slack, with zero failing endpoints in all reported internal timing categories. Each image passes three cold-programmed runs on the remote PG2L200H platform. All six complete UART benchmark frames match full RTL simulation byte-for-byte, including cycle counts, retired instructions, CRCs and cache statistics. Both separately implemented 115,200-baud images pass local qualification with +0.158 ns setup slack and +0.100 ns minimum hold slack; complete hardware qualification applies to the 9,600-baud images.

Earlier remote captures lost output or contained NUL corruption and remain excluded. Some gateways take approximately 0.3 seconds per read and can return at most 512 bytes. The slower-UART physical profile and paced host polling produced the complete accepted captures, using the same benchmark firmware and CPU clock. UART rate and polling settings are recorded in the manifests. Capture validation does not remove corruption or reconstruct missing fields; these successful repetitions are not a claim that the remote transport is universally reliable.

The accepted RV32IM reference is `accepted-153-valid-ram-v31-r1/accepted_valid_ram`. Its source and results are preserved. The new implementation lives in this directory; its standalone top is `fpga/pds_soc_top.v`. Generic RTL parameter defaults do not describe the release configuration.

## Performance evidence

| Metric | Accepted RV32IM | Qualified RV32IMC |
| --- | ---: | ---: |
| Configured clock | 153 MHz | 153 MHz, timing qualified |
| CoreMark V0 iterations | 6,000 | 6,000 |
| Timed V0 cycles | 1,793,942,498 | 1,782,669,419 |
| Retired V0 instructions | 1,649,428,429 | 1,649,428,429 |
| CoreMark at the configured clock | 511.722088, hardware validated | 514.958068, RTL and hardware verified |
| CoreMark/MHz | 3.344589 | 3.365739 |
| Timed V1 cycles | 1,793,507,264 | 1,784,414,808 |
| Retired V1 instructions | 1,649,775,527 | 1,649,775,527 |

The V0 throughput improvement is 0.6324%. Both seed configurations pass the CoreMark CRC checks and exceed ten seconds at the stated clock. The simulation observer independently checks timing and retirement counters; all six hardware runs reproduce those counts. UART is accelerated in simulation and is outside the timed benchmark interval.

The accepted implementation uses 6,851 post-route LUTs, 3,331 FFs, 21 DRM and four APM. Its resource efficiency is 0.0746930503 CoreMark/LUT. The current timing-qualified 115,200-baud images use 6,638 LUTs, 3,007 FFs, 21 DRM and four APM. The original 0.150 ns setup uncertainty remains in force.

The 9,600-baud V0 profile uses 6,640 LUTs, 3,015 FFs, 21 DRM and four APM. It passes with +0.090 ns setup slack and +0.100 ns minimum hold slack. Its resource efficiency is 0.0775539259 CoreMark/LUT, a 3.8302% improvement. LUT count decreases 3.0798% and FF count decreases 9.4866%. These resource numbers belong to the slower-UART image; the two physical profiles are reported separately.

## Current source-bound evidence

Paths in this table are relative to `cpu_paper/results`.

| Evidence | Artifact | Outcome |
| --- | --- | --- |
| Full V0 | `rvc-coremark-20260930T153155Z-ec52846a` | Pass; 1,782,669,419 cycles |
| Full V1 | `rvc-coremark-20260930T153155Z-eb6ed028` | Pass; 1,784,414,808 cycles |
| Default ISA/system suite | `rvc-isa-20260930T152849Z-b3ec6546` | 50 programs pass |
| Cache disabled | `rvc-isa-20260930T153155Z-be37b3b6` | 50 programs pass |
| Fast cache responses disabled | `rvc-isa-20260930T153155Z-44cc4353` | 50 programs pass |
| Prediction disabled | `rvc-isa-20260930T153155Z-0fb51526` | 50 programs pass |
| Decoder and frontend | `rvc-frontend-tests-20260930T145958Z-88697c17` | 49,152 decoder encodings; 480,000 randomized cycles at each of two address widths |
| Cache | `rvc-cache-tests-20260930T134722Z-da85035c` | Nine configurations pass, including capacity and writeback checks |
| Predictor equivalence simulation | `rvc-predictor-tests-20260930T145956Z-0272a0da` | 1.4 million comparisons across seven configurations |
| FIFO/UART/MMIO | `rvc-peripheral-tests-20260930T124116Z-8adf53e9` | All three testbenches pass |
| Multiply/divide and precomputed product | `rvc-muldiv-tests-20260930T153042Z-0c42b29d` | 12,544 arithmetic checks and 10,998 precomputation checks pass |
| Regression source audit | `rvc-regression-audit-20260930T155220Z-473c400a.json` | Frozen tested modules match the timing-qualified 9,600-baud physical inputs and working RTL |
| V0 physical, 115,200 baud | `rvc-physical-20260930T152846Z-610b3076` | Internal timing passes |
| V1 physical, 115,200 baud | `rvc-physical-20260930T153432Z-c09535cd` | Internal timing passes |
| V0 physical, 9,600 baud | `rvc-physical-20260930T154321Z-f13639d6` | Internal timing passes |
| V1 physical, 9,600 baud | `rvc-physical-20260930T155103Z-954b3c4f` | Internal timing passes; same resources and slack as V0 |
| Local acceptance assessment | `rvc-assessment-20260930T155151Z-c35ff2e3.json` | All source, performance, timing and resource gates pass |
| Standard-UART local assessment | `rvc-assessment-20260930T155912Z-6fb98aed.json` | All local gates pass for the separate 115,200-baud profile |
| V0 hardware | `rvc-board-20260930T160047Z-100525f0` | Three cold programs; all complete frames match full RTL |
| V1 hardware | `rvc-board-20260930T160619Z-4d26cac3` | Three cold programs; all complete frames match full RTL |
| Final hardware/RTL assessment | `rvc-assessment-20260930T160940Z-b1cec92d.json` | `board_and_rtl_verified`; every acceptance check passes |
| Firmware reconstruction | `rvc-firmware-rebuild-20260930T143943Z` | V0 and V1 rebuilt byte-for-byte from frozen software inputs |

The firmware reconstruction matches the earlier full-run firmware. Current invocations of `run_rvc_coremark.py` compile frozen software copies directly and record compiler identity, commands and input hashes. The completed predecessor full runs are `rvc-coremark-20260930T150451Z-e3dc81bd` (V0) and `rvc-coremark-20260930T150451Z-14d45363` (V1).

## Images and reproduction

The remote-capture images are the `implementation/generate_bitstream/pds_soc_top.sbit` files inside the two 9,600-baud physical directories listed above. V0 is the performance-seed image; V1 is the validation-seed image. Their corresponding firmware is in `firmware/V0/firmware.hex` and `firmware/V1/firmware.hex` under the current full simulation directories. Each physical manifest records the firmware and bitstream SHA-256 digests.

The physical wrapper in the working variant defaults to 115,200 baud. Reproduce the remote-capture profile with native Windows Python using `run_rvc_physical.py --firmware <firmware.hex> --profile packing3_compact0 --seed 2 --uart-baud 9600`. The runner creates a fresh project, copies the inputs and records all physical reports. It does not modify the working wrapper or accepted baseline.

For hardware capture, use `run_rvc_board.py --physical <physical directory> --screen <current short CoreMark directory> --firmware <matching firmware.hex> --repetitions 3`. The runner checks timing and source identity before programming, preserves any pre-existing reservation, opens UART at the frozen physical rate and sends ASCII `G` to start CoreMark. The accepted captures use 512-byte reads: V0 uses the default 100 ms host polling delay, while V1 uses `--poll-delay-ms 200`. These delays are outside the CPU benchmark and change neither firmware nor the measured cycle interval. Both reservations were released after capture.

Complete output is required. The board runner preserves raw bytes and rejects NUL corruption. The final assessor also compares every complete benchmark frame byte-for-byte against full RTL output, in addition to checking CRCs, cycle counts, retired instructions and cache statistics. It does not sanitize the frames.

## Rejected capture attempts

The following runs remain preserved and are excluded from qualification. Capture failures do not establish a CPU computation failure; conversely, correct surviving fields do not qualify an incomplete or corrupted run.

| Artifact | Reason for rejection |
| --- | --- |
| `rvc-board-20260930T153432Z-a0f5935d` | 115,200-baud output lost benchmark fields |
| `rvc-board-20260930T153959Z-5e49872b` | 115,200-baud capture did not receive the finish marker |
| `rvc-board-20260930T155044Z-724b7847` | NUL bytes interrupted the cycle-count field |
| `rvc-board-20260930T155313Z-731dac7a` | Two complete V0 frames matched RTL; the third contained NUL corruption |
| `rvc-board-20260930T155653Z-2d25f7cb` | 64-byte reads lost output on a slower gateway |
| `rvc-board-20260930T155824Z-7ca3d1d2` | NUL corruption, including a frame whose numeric fields passed but whose full raw text failed comparison |
| `rvc-board-20260930T160338Z-cdd5377f` | Two clean V1 frames; the third contained NUL corruption and the set was rejected |

The negative assessment `rvc-assessment-20260930T160138Z-aac24402.json` confirms that partially successful runs and corruption outside the numeric fields do not satisfy the final acceptance gates.

## Interpretation and limits

The historical accepted benchmark used a relocated UART-loader image. The compressed standalone firmware links at zero. The complete implementation also changes predictor history and several control structures. The overall score difference must therefore not be attributed solely to compression.

A same-layout, ten-iteration RV32IM control takes 2,960,668 / 2,957,270 cycles, compared with 2,975,495 / 2,978,961 for RV32IMC. These short controls do not show a C-only execution-speed improvement and are not reportable CoreMark scores. The short V0 text segment shrinks from 22,752 to 19,166 bytes. Compression's code-size benefit is established separately from throughput. The current control evidence is `rvc-coremark-20260930T153155Z-bf7aaa26`; compressed short evidence is `rvc-coremark-20260930T152849Z-0214ee3a`.

Scores in this document use `iterations * configured_clock_hz / cycles`. The port's legacy integer-seconds `Iterations/Sec` console field is not used; it loses fractional elapsed time. Raw cycle counts and CRC fields must be present in an accepted capture.

The compressed decoder supports the integer RV32C instructions appropriate to RV32IMC, including legal hints and reserved/illegal encodings. Machine traps preserve halfword-aligned return PCs and raw illegal-instruction values. Directed tests cover the second-half access fault at the RAM boundary, FENCE.I, and software/timer/UART interrupts. These simulations are substantial regression evidence, not a formal proof of ISA compliance.

Physical qualification checks the existing internal clock constraints at all reported corners. The configured PLL rate is not an independent frequency measurement, and no experimentally measured maximum clock or power claim is made. The accepted board executions use the exact timing-qualified images and match full RTL for both seed configurations. The asynchronous reset/key/UART RX exceptions and the absence of synchronous external timing specifications for LED/UART TX remain the same as the accepted reference; internal timing closure does not add an external interface timing guarantee.
