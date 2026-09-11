# 153 MHz project handover — human-readable version

## Status and scope

**Provisional validation complete on September 11, 2026.** The selected complete implementation is `cpu/experiments/full_fetch_commit_factored`, not the older top-level CPU or an experiment selected by the highest clock in its name.

The user explicitly accepts **local ILA validation** because the remote platform has limitations. The stopping criteria are successful local ILA checks, successful remote hardware bring-up, two handover documents and one authorized GitHub snapshot. Further optimization is paused; AI acceleration remains deferred. This is provisional project acceptance, not exhaustive ISA, environmental, electrical or official competition certification.

Read `AI_HANDOFF_153MHZ.md` when continuing in another AI conversation. This document supersedes older present-tense or running-state entries elsewhere in the repository.

## Final metrics

| Measure | Accepted performance result | Basis |
| --- | ---: | --- |
| Configured operating frequency | **153 MHz** | PLL configuration and passing complete native PDS implementation |
| Execution efficiency | **3.341946923 CoreMark/MHz** | Hardware timed cycles, not rounded printed seconds |
| Resource efficiency | **0.053811605896 CoreMark/LUT** | Hardware score divided by **9502 complete-system LUTs** |
| CoreMark throughput | **511.317879224** | 6000 iterations / 11.734383333 seconds |
| Complete resource count | **9502 LUT / 5079 FF** | Post-route CLMA plus CLMS; ILA and peripherals included |
| Worst setup slack | **+0.021 ns** | Complete 153 MHz implementation; narrow margin |

Frequency is the configured clock, not an independently measured oscillator frequency or proven maximum over voltage and temperature. Do not substitute PDS's 153.5155 MHz estimate for a tested clock. Do not use ordinary non-ILA area (9075 LUT) in the complete-system efficiency calculation.

The previous hardware baseline was 157.5 MHz, 501.065730222 CoreMark, 3.181369716 CoreMark/MHz and 0.053452712846 CoreMark/LUT (9374 LUT). The new measured score improves **2.0461%**, execution efficiency **5.0474%**, and resource efficiency **0.6714%**, with a **2.8571% lower clock**. This meets the permitted clock tradeoff and nondecreasing throughput/resource-efficiency floors. Relative to the intermediate local 151.2 MHz candidate, resource efficiency is 0.0885% lower; not every metric improved over every experiment.

## What remains in the system

The selected implementation retains the RV32 integer processor and M extension, pipeline and branch prediction, instruction/data caches, timer/counters, UART, GPIO and the complete ILA. The configured instruction cache is 16 KiB; firmware reports 64 KiB on-chip main memory. No peripheral was deleted to improve the denominator.

The ILA has **42 data channels, 33 trigger channels and 1024 samples**. Its data contains the 32-bit EX PC plus pipeline valid/transfer/flush/fetch signals. The scope application is separate: software samples two GPIO inputs into a 256-record buffer and exports timestamps/pin values over UART. A scope GPIO capture is not a 42-channel ILA capture.

The last CPU change factors equivalent fetch-commit enables. It is not a benchmark-specific instruction substitution, reduced validation workload or removal of debugging functions. The evidence includes the exact implementation source-hash inventory.

## Hardware measurement

On September 11, the verified full images were programmed into **Experiment box 1, device 12, PG2L200H** on the remote FPGA platform. Each programming operation reported successful transfer and burn. UART was configured at 115200 baud, 8N1. ASCII G started the CoreMark firmware. Both terminal outputs, per-packet hexadecimal bytes and decoded text were retained and checked.

| Run | Iterations | Timed cycles | Retired instructions | Seed / final CRC | Result |
| --- | ---: | ---: | ---: | --- | --- |
| Performance V0 | 6000 | 1795360650 | 1649428424 | e9f5 / a14c | 511.317879224 CoreMark |
| Validation V1 | 6000 | 1795883504 | 1649775523 | 18f2 / 18e1 | 511.169014001 iterations/s |

Both runs exceed ten seconds at the configured clock, pass the expected algorithm CRCs and exactly match their source-bound long RTL run cycles, retired counts and cache profiles. The performance score uses V0; do not average the two seed scores.

**Use the checked cycle-derived result.** The legacy integer-format CoreMark output prints `Iterations/Sec : 545` and whole seconds. That is not the accepted score. The verifier uses the untruncated `ZGTC cycles_hex` and `clock_hz` fields: `6000 * 153000000 / 1795360650`. The firmware and compiler were not changed during closure to hide this formatting limitation. Compiler: GCC 10.2.0, RV32IM, O3, loop unrolling and linker relaxation; full flags remain in the UART record.

The complete scope image also passed a hardware smoke test: command processing, EMPTY, ARMED and an actual approximately 30-second TIMEOUT. Its help response was truncated by the platform receive path; this is recorded, not presented as lossless waveform export. Complete UART-byte decoding, GPIO pulse capture and checksum behavior pass the source-bound local application test. A hardware scope waveform capture is not claimed.

The UART was closed and the device was released after testing. No device is intentionally left reserved.

## Local ILA validation

The current CPU and exact ten-iteration diagnostic firmware were captured at each ELF-resolved list, matrix and state algorithm entry. Each window contains **1024 samples across all 42 logical data channels**, with **1023 temporal transfer checks**. Checks reject malformed widths, indexes, sample counts, MEM transfer without a valid instruction and WB without the preceding MEM transfer. The complete diagnostic benchmark result remains unchanged by the observation ports.

All three windows and four capture test methods pass. The matrix 16-cycle SVG was visually reviewed. Window occupancy and WB counts are local observations, not global IPC or exclusive stall-cause measurements.

These are **RTL logical-channel captures**, not data read from physical DebugCore capture RAM. Separately, native FabricInserter mapping and complete post-route timing/resource audits pass for all three images. The remote UI exposed only 33 trigger channels when importing the 42-data/33-trigger FIC. No remote ILA acquisition was started or declared successful. Under the clarified criterion, that platform limitation does not block provisional completion.

## Verification inventory

- Source-bound local long V0/V1 runs and complete native PDS images pass, including exact source, firmware, parameter, clock, ILA and area binding.
- Prior current-source regression evidence includes 196 pinned upstream RV32UI/RV32UM executions across four configurations and eight rejection controls. Misaligned-data coverage checks an expected precise trap, not transparent misalignment support or exhaustive certification.
- Fetch factoring has directed, random paired-core, state-transition and core/cache regression evidence. Rejected experiments remain historical records, not alternative accepted builds.
- Local application validation covers two captures, UART 0x55 decode, GPIO pulses, EMPTY, timeout, checksum, no late samples and ready status. Its accelerated timeout uses explicit counter jumps; the hardware smoke timeout is separate evidence.
- Four local ILA capture tests and five new hardware packet-integrity, failed-burn and wrong-device negative-control tests pass.
- A bounded synchronizer-structure audit passes for the relevant UART/GPIO/reset chains. This is not whole-design CDC or MTBF certification.

## Files to use

| Purpose | Repository path |
| --- | --- |
| Qualified experiment | `cpu/experiments/full_fetch_commit_factored/` |
| Human handover | `cpu/docs/PROJECT_HANDOVER_153MHZ.md` |
| AI continuation handover | `cpu/docs/AI_HANDOFF_153MHZ.md` |
| Acceptance chronology | `cpu/docs/ACCEPTANCE.md` |
| Portable evidence | `cpu/docs/evidence/153mhz-20260911/` |
| Fresh-clone evidence verifier | `cpu/scripts/verify_153mhz_handoff.py` |
| Local packet/source auditor | `cpu/experiments/full_fetch_commit_factored/audit_fetch_hardware.py` |
| Electrical caveats | `cpu/experiments/full_fetch_commit_factored/LOCAL_ELECTRICAL_REVIEW.md` |

From the repository root, run:

`python cpu/scripts/verify_153mhz_handoff.py`

This uses published text evidence and sources; it needs neither a browser session nor PDS or ignored build directories. It verifies archive consistency, not a new FPGA experiment.

On the original workstation, full raw records are under `cpu/build/hardware/fetch-commit153000-20260911-box1/`. Full local captures are under `cpu/experiments/full_fetch_commit_factored/build/ila-pipeline-rtl/fetch-commit153000/`. Raw sessions and generated tool databases remain local; compact UART logs, capture CSVs, SVGs, summaries and hashes are published as documentation.

## Exact programming images

All paths below are relative to `cpu/experiments/full_fetch_commit_factored/build/ila/`, with filename `generate_bitstream/pds_soc_top.sbit`.

| Role / stage | SHA-256 |
| --- | --- |
| V0: fetch-commit-seed1-native-wb | 5BBBEA849F5E3E51576927641FC7DC00393862D6BD9CB3638C3769E7FF757DB1 |
| V1: fetch-commit-v1-seed1 | 441DA777607E2C16FF7FA19671A1618473B24783F05EC44B1C70974F3BAF3018 |
| Scope: fetch-commit-scope-seed1 | D2D91235C09FF5C5D7E9639AA6887AF8642FFEA82B4AA441D580711C7CEEFF6F |

Generated bitstreams are not included in the source snapshot. Preserve original local artifacts for exact reprogramming. Another tool version, seed or source state produces a new artifact and requires fresh qualification.

## Limits and stopping rule

PDS still warns that SCBV is unset. Board configuration-power evidence, full electrical/CDC acceptance, independently measured clock, long-duration stability and voltage/temperature margin are not signed off. The +0.021 ns setup margin warrants caution. Successful programming and UART results do not resolve those questions.

The snapshot preserves accumulated source, tests, scripts and documentation, excluding PDS databases, generated binaries, large local build trees and credentials. Historical scripts often refer to fixed, ignored parent build receipts and local toolchain paths. A clean clone supports the published evidence check, but is not a fully hermetic one-command rebuild of every experiment. Follow the AI handoff before reconstructing a build; a missing historical receipt is not a hardware failure.

Stop optimization after this authorized snapshot. Do not resume H4 prediction experiments, replace top-level RTL, repeatedly reserve hardware or push additional commits unless requested. The two handover documents and evidence index define the provisional endpoint.
