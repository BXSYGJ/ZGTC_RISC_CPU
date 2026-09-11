# Timed execution profile of the complete control-commit candidate

Date: September 10, 2026. This profile observes the unchanged C1E4F75D CPU, not a new scoring implementation.

## Reproduction and evidence boundary

Run profile_execution.py through WSL Python from PowerShell. It creates build/execution-profile-current once and refuses to overwrite it. It reuses the existing byte-locked retirement observer from the project's load-use profiler. Only the simulation C++ observer differs from the verified short-run inputs; every RTL source and firmware byte stays unchanged. The original short run is build/compiled/20260910-195856-6bf511dd.

The runner verifies the actual ELF image against the loaded firmware, derives the start_time/stop_time mcycle-read PCs from disassembly, and checks every retired instruction against firmware. Its complete UART bytes and parsed counters/CRCs match the original short run. The initial attempt failed before creating the output directory because the root parser does not admit this experimental clock; the corrected runner imports the candidate's clock-aware parser. Both logs are preserved.

analyze_execution.py revalidates the trace, metadata, executable, firmware, observed inputs and current non-observer source hashes. It reuses retirement_gap_profile.summarize_records, whose axes each conserve the same interval count and elapsed cycles. The axes are alternative groupings, not quantities to add together.

## Actual timed V0 observation

- Timer-read PCs: 0x5a70 and 0x5a8c; sampled cycle counters 43281 and 3104154.
- Timed span: 3060873 cycles, exactly the reported short CoreMark interval.
- Trace records: 2748929, including the two timer boundaries. This is not the separate firmware retired-counter result of 2748941; the two measurements use different instruction boundaries.
- Extra interval cycles above one cycle per adjacent retirement: 311945. This is arithmetic overhead, not proof that every extra cycle is independently removable.
- Intervals following conditional branches account for 276369 of those extra cycles (88.5954%). JALR-following intervals account for 10076, JAL-following intervals 6960, and other preceding instructions 18540. These groups do not directly measure mispredictions or attribute stall causes.
- All 93960 timed M-extension instructions are low MUL. No MULH, MULHSU, MULHU, DIV, DIVU, REM or REMU appears in this V0 trace. Of the low MUL retirements, 90674 have a one-cycle preceding gap, 3251 have two cycles, and 35 have nine cycles. This is not a direct count of precompute hits.

The largest individual gap contribution is the 0x514 -> 0x518 branch fall-through: 2040 observed occurrences with six-cycle retirement gaps, contributing 10200 extra interval cycles. Several other dominant transitions are in the 0x49xx-0x4cxx region. A next-step predictor experiment is justified; more high-multiply/divide latency work is not justified by this particular timed stream.

## Follow-up experiment

../full_history4 changes only the default local-history width from three to four bits in rv32_btb. It retains 256 entries, two-bit counters, the same hash/target/tag semantics, GPIO, UART and intended full 42/33/1024 ILA. Sixteen pattern banks replace eight; this has a real potential resource/timing cost, not free accuracy.

Both paired ten-iteration RTL runs improve versus this parent with identical firmware, retired counters and CRCs: V0 3060873 -> 3053191 cycles, V1 3065630 -> 3060950. These are throughput improvements of 0.251606% and 0.152894% for these short tests only. No long-run, post-route efficiency or hardware improvement follows from these values alone. See the isolated candidate README for subsequent physical results.

The full history-four build subsequently failed timing at -0.072 ns and used 9663 LUT, versus this parent's 9406. It retains the actual 42/33/1024 ILA but is rejected at the tested physical point. This measured cost prevents treating its short-run gain as an overall upgrade. The parent remains unchanged.
