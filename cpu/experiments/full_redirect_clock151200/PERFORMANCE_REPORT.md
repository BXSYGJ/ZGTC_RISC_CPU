# Current full-system performance and application report

## Scope and evidence

This report covers experiments/full_redirect_clock151200, CPU SHA256 81671AD0A87EBD75F68D6351A85DAA21899CA42D27472B4C5B325F59EA8ABDEE. Topic 1 requirements were rechecked against PDF pages 10-11 of the supplied topic guide. The three scored dimensions are execution efficiency, clock frequency and resource efficiency. CoreMark throughput is an additional user-imposed minimum, not a replacement for clock frequency.

The new results are local RTL-derived performance projections combined with actual full-ILA PDS timing and resource reports. DC90363D remains the board-validated baseline. No current-candidate board score, measured oscillator frequency, absolute physical performance limit or complete contest acceptance is claimed.

## Performance and tradeoff

| Quantity | DC90363D board baseline | Current local candidate | Change |
| --- | ---: | ---: | ---: |
| Configured clock frequency | 157.5 MHz | 151.2 MHz | -4.0000% |
| Execution efficiency | 3.181369715697977 CoreMark/MHz | 3.337708280819477 CoreMark/MHz | +4.9142% |
| Resource efficiency | 0.053452712846429634 CoreMark/LUT | 0.053859284104579 CoreMark/LUT | +0.7606% |
| CoreMark throughput | 501.0657302224314 | 504.6614920599049 | +0.7176% |
| Full-system post-route LUT | 9374 | 9370 | -4 |

For iteration count N, measured RTL cycles C, configured physical frequency F in Hz and full-system LUT L: execution efficiency = N * 1000000 / C; throughput = N * F / C; resource efficiency = throughput / L. Exact rational comparisons enforce both baseline floors. Timing passes at the stated configuration, but does not establish the highest achievable frequency or frequency stability across devices, supply or temperature.

The paired 6000-iteration runs are V0 20260911-001254-0e98e281 (1797640625 cycles, 1649428424 retired instructions, CRC a14c, 11.889157572751323 modeled seconds) and V1 20260911-001315-6a0c1e04 (1799846469 cycles, 1649775523 retired instructions, CRC 18e1, 11.903746488095239 modeled seconds). Both pass CRC and the ten-second duration requirement. The audit re-parses complete UART output and checks the exact captured sources, compiler command, firmware, executable and result hashes. It does not score partial progress logs.

Relative to full_control_commit, the V0 timed loop saves 33931518 cycles and execution efficiency improves 1.8876%. The clock tradeoff reduces throughput by about 0.1502% relative to that local predecessor; it nevertheless remains above the governing DC90363D baseline and improves resource efficiency. See build/long-comparison.json and build/local-joint-score-resource-qualification.json.

## Complete physical images

All three passing full-ILA images use 9370 LUT / 4986 FF and have setup WNS +0.017 ns at configured 151.2 MHz. This is a narrow nominal timing margin. GPIO, UART, 42 data channels, 33 trigger channels and 1024 samples remain present. No debug or peripheral area is subtracted.

| Image | Full-ILA build | Bitstream SHA256 |
| --- | --- | --- |
| V0 benchmark | 20260910-redirect-clock151200-seed1 | ED45D1C8D1678E0C70C671AEAC086415CA4D7EBFD66FBD8AD7A3EA4453D7B556 |
| V1 validation | 20260911-redirect-clock151200-v1-seed1 | 1C93B95632E9B6DB6F01C72D0968840F37500718F7CFDAB8F8E6AFEC46F31B23 |
| Scope application | 20260911-redirect-clock151200-scope-seed1 | C2A21D376B9F0FD48AC0D8B107CE2E053D1FFCD2C6884352A13637C09A81B7CE |

Ordinary implementations and the full-ILA seed-2 retry failed timing; their reports remain recorded. Their smaller or different resource counts are not substituted into the passing-image score. Native Inserter output and source-to-net mapping, not only a configuration file, establish the preserved ILA dimensions.

## Algorithm pipeline waveforms

The current-source observer captures three 1024-cycle windows with the same 42 logical channels as the physical ILA. The linked ELF is byte-checked against the actual short-run firmware. Adding observer outputs leaves the complete short CoreMark result unchanged: 3004340 timed cycles, 2748941 retired instructions and the same CRC/profile. Each window checks 1023 adjacent ID-to-EX / EX-to-MEM transfers; the candidate auditor also checks MEM fire/valid and WB following MEM fire. These are RTL observations, not samples read from the physical DebugCore RAM.

| Algorithm window | WB events / 1024 cycles | Local WB-event rate | EX held cycles | MEM held cycles |
| --- | ---: | ---: | ---: | ---: |
| core_bench_list | 736 | 0.7187500000 | 117 | 108 |
| core_bench_matrix | 483 | 0.4716796875 | 299 | 299 |
| core_bench_state | 563 | 0.5498046875 | 41 | 40 |

The matrix window exhibits substantially more held EX/MEM cycles than the other two windows. The signal set cannot attribute those cycles uniquely to loads, multiplication, bus wait states or other causes. The 16-cycle matrix zoom shows bubbles followed by sequential stage activity. Local window rates are not whole-benchmark IPC, and the windows are not identical instruction streams across implementations.

Full CSVs, SVGs and 16-cycle zooms: build/ila-pipeline-rtl/redirect-prime151200. The matrix zoom and scope UART preview were rendered and visually checked locally, without browser or board access. See EXECUTION_PROFILE.md for the separate complete retirement-stream comparison: 56533 short-run intervals save one cycle, none worsen, and branch-following intervals account for 222661 of the remaining 255412 extra cycles. This supports branch/dependency-cause instrumentation as the next optimization step; it does not prove all those cycles are removable.

## Application scenario

The processor controls a two-channel GPIO waveform acquisition application with UART control and result output. Firmware SHA256 72BE13E1AABEDFBEDF7EA2DE4A97DC49ECA020FDB2158DA64582ADF89C32655E uses configured 151200000 Hz, 1210-cycle requested sampling and a 4536000000-cycle timeout. Runtime 20260911-010153-3367fed2 completes in 2693243 simulation cycles with two 256-sample dumps, UART 0x55 decode, GPIO transitions 0/1/0, zero late samples, EMPTY behavior and timeout behavior.

The timeout test advances the 64-bit cycle counter across 2^32 and to the 30-second threshold; it is not thirty seconds of wall-clock or physical-board testing. UART simulation parameters are accelerated and explicitly recorded. audit_application.py binds runtime, physical parameters, current and captured RTL, firmware and the separately passing scope bitstream. build/local-application-qualification.json passes local pairing but keeps hardware_validated and electrical_qualified false.

The preceding runtime 20260911-004616-9388dcd0 reached the same testbench PASS but failed host decoding because the supported-clock list omitted 151200000. The decoder fix has positive current-clock and wrong-clock rejection tests. The failed manifest is retained; the fresh completed run, not a relabeled failure, supplies application qualification.

## Remaining acceptance and optimization work

The next source-bound internal-event observation is now complete; CONTROL_EVENT_PROFILE.md records the exact WB-gap and EX-state conservation checks, actual early/late redirects and two slower correlation variants. Neither variant is promoted. This diagnostic supersedes the earlier proposal to add internal event observation, but does not change the qualified metrics or close electrical/board acceptance.

The three basic tasks (RV32I core, at least three pipeline stages, UART/GPIO integration), advanced two-way I/D cache with burst transfers, and dynamic prediction with machine-mode exception/interrupt handling remain required. The current physical RTL inventory is identical to the tested full_redirect_prime inventory; the separately recorded clock/firmware changes are not new ISA or exhaustive exception certification. Source-bound functional regressions and current application/benchmark tests are evidence, not a proof covering every architectural state.

AI acceleration alone is deferred. Complete task/documentation closure, board-specific electrical/configuration-power evidence and eventual current-image hardware validation remain open. The bounded native synchronizer checks pass for UART, GPIO and reset; they do not prove complete CDC coverage, MTBF, routed placement or reset recovery/removal. VCCIOCFG, VCCIOL4/L5, configuration mode, actual board revision and SCBV wiring must not be guessed. Chrome 19476 remains unused under the user's pre-qualification gate.

Next optimization should identify the remaining branch-following bubbles with source-bound internal event observation, preserve full GPIO/UART/ILA functionality, and evaluate both cycle savings and physical resource cost before promotion. The 17-ps timing margin also warrants further placement/critical-path work; a higher estimated clock or a short run alone cannot qualify a new version. No GitHub publication is performed without a new request.
