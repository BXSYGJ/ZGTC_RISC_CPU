# Execution-efficiency profile: complete 153 MHz candidate

## Evidence and boundaries

September 11, 2026. The CPU, caches, GPIO, UART and ILA-capable source remain unchanged. The existing nonintrusive C++ observer replaces only the simulation driver in an isolated stage; it reads the existing retirement interface. No profile instrumentation is added to the FPGA.

Both ten-iteration runs reproduce their corresponding non-profiled raw UART byte for byte, including cycles, retired counts and CRC. Timer-boundary PCs are extracted from the matching ELF and checked against the loaded firmware. The independent auditor checks exact compilation/invocation arguments, all captured sources, executable/firmware hashes, trace boundaries, record contents and cycle conservation. Four negative-control methods reject configuration/source changes, UART changes, timer-boundary/span changes and altered compiler arguments.

These are short exploratory traces, not reportable CoreMark runs or internal stall/misprediction counters. Each axis partitions the same retirement intervals; never add different axes. A gap above one cycle is arithmetic overhead, not a proof that every extra cycle can be independently eliminated.

## Observations

| Observation | Performance seed | Validation seed |
| --- | ---: | ---: |
| Retired trace records | 2748929 | 2749602 |
| Timed cycle span | 3000565 | 3001255 |
| Extra cycles over one per retirement interval | 251637 | 251654 |
| Extra cycles in intervals following a conditional branch | 222661 | 224805 |
| Share of arithmetic overhead following conditional branches | 88.485% | 89.331% |
| Extra cycles in intervals with an adjacent load dependency | 5495 | 4416 |

The last row is a different partition and must not be added to the branch row. Most adjacent load-address and load-branch dependencies already retire with one-cycle gaps in these traces; the small remaining load-dependency category is not the first optimization priority. The trace record count is not equated to the separately sampled UART minstret delta.

## Next optimization direction

Prioritize a general-purpose branch-prediction or redirect-recovery improvement, not benchmark-PC special cases. First distinguish actual prediction errors, target misses and fetch/redirect backpressure using the existing predictor event observer or a separately verified nonintrusive observer. Retirement adjacency alone cannot distinguish these causes.

For example, the performance-seed transition 0x0514 -> 0x0518 occurs 2040 times with five-cycle retirement gaps, contributing 8160 extra cycles. This identifies a useful diagnostic site, not permission to hard-code that address or change CoreMark. Broad predictor or pipeline changes must preserve ISA behavior, whole-system peripherals and the full ILA, then pass both short screens, complete native timing/area and the paired 6000-iteration qualification.

## Reproducible artifacts

- retirement-profile/20260911-110916-6c2c9a5e/invocation.json: performance seed; trace SHA256 24EE452AA820CBCD713A040ADC540ADD5215EFAD9B75BE502EA7745C622B6759.
- retirement-profile/20260911-111218-b6578bc4/invocation.json: validation seed; trace SHA256 B415F9428E82A4AB4F3B72E3EA83A7C33250F2B76461DB8B00B3B919FF3DCE87.

Use run_fetch_profile.py for a new isolated performance trace, or add --validation for the validation seed. audit_fetch_profile.py takes the completed profile directory and replays the source/command/trace checks. Each directory contains retirement-gaps.json with complete partitioned histograms and ranked PC transitions.
