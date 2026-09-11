# Current-core control-event profile

## Measurement boundary

profile_control.py observes the current 81671AD0 CPU using the unchanged ten-iteration V0 firmware from build/compiled/20260910-233631-e15b5716. Only the copied simulation SoC output ports and C++ observer change. The actual synthesized CPU, GPIO, UART and 42/33/1024 ILA images are untouched. The source-bound compiler command keeps every original hardware parameter. The complete UART result and the original timer-bounded retirement trace are byte-identical.

The binary trace contains exactly 3004340 records, one before each clock edge over the half-open interval [43087, 3047427). Each little-endian 20-byte record contains cycle, EX PC, MEM PC and 32 named internal signal bits. analyze_control.py reconstructs the exact source instrumentation, verifies current and captured input/output hashes, and checks cycle order, interval length, fire/valid relations and WB following MEM fire. This is an RTL diagnostic, not a new score or physical-ILA capture.

## Conserved counts

| Observation | Count |
| --- | ---: |
| Timed cycles | 3004340 |
| WB events in the half-open interval | 2748928 |
| Cycles without a WB event | 255412 |
| EX empty cycles | 237186 |
| EX fire events | 2748928 |
| EX occupied but blocked cycles | 18226 |
| Early redirect events | 53021 |
| MEM flush events | 3735 |
| Interrupt-pending cycles | 0 |
| Redirect-prediction-pending cycles | 56533 |

WB-empty cycles exactly match the 255412 extra cycles in the separately verified retirement-gap analysis. EX empty + EX fire + EX blocked exactly conserves all timed cycles. These are different views of overlapping pipeline activity; adding WB-empty and EX-blocked counts would double-count time.

Blocked EX cycles are classified using explicit priority: interrupt drain, older flush, memory stage not ready, load-use wait, serial drain, then multiply/divide result wait. The observed partition is 3733 older-flush cycles, 5908 memory-not-ready cycles, 5330 load-use cycles, 4 serial-drain cycles and 3251 multiply/divide-wait cycles. No cycle remains unclassified. This priority partition is not an additive estimate of removable performance cost.

## Control-flow hotspots

Conditional control instructions produce 524173 MEM events, 51779 early redirects and 2092 MEM flushes. Unconditional control instructions produce 59501 MEM events, 1242 early redirects and 1643 MEM flushes. Raw branch conditions are counted only with the corresponding stage fire event; stale decode bits are not treated as instructions.

| PC | EX/MEM control events | Early redirects | MEM flushes |
| --- | ---: | ---: | ---: |
| 0x49b8 | 9680 | 3240 | 0 |
| 0x4a0c | 14800 | 2560 | 0 |
| 0x514 | 61200 | 2060 | 0 |
| 0x4bc0 | 12640 | 1760 | 0 |
| 0x4ec | 28870 | 0 | 940 |
| 0x84c | 27780 | 0 | 890 |

The firmware-bound ELF places 0x49b8, 0x4a0c and 0x4bc0 in core_state_transition (start 0x493c, size 0x318). At 0x4ec and 0x84c every observed EX control event has early_load_dependency asserted, consistent with the current early-redirect guard deferring these branches. This observation does not measure how much timing margin an early-load bypass would consume. Redirect counts alone do not establish BTB hit rate, pure direction-prediction accuracy or a universal per-redirect cycle penalty.

## Correlation experiments

Both isolated variants keep the original full SoC and exact firmware/compiler settings in their paired ten-iteration screens, changing only rv32_btb.sv. They retain the per-entry counter-bank count; neither has a new physical implementation or resource measurement.

| Variant | V0 cycles | V1 cycles | V0 / V1 cycles saved versus current |
| --- | ---: | ---: | ---: |
| Current local-history predictor | 3004340 | 3007840 | 0 / 0 |
| Three-bit global XOR local history | 3030448 | 3030297 | -26108 / -22457 |
| Latest global bit XOR oldest local bit | 3004793 | 3008116 | -453 / -276 |

All four complete CoreMark screens pass CRC, preserve retired counts and retain their source, executable, firmware and log hashes. Both experiments pass 72 predictor parameter configurations and 24 compiled negative controls, plus two observationally equivalent unconditional-history cases. The one-bit experiment initially exposed insufficient mutation-test coverage: single-branch sequences did not distinguish frozen or incorrectly unconditional global updates. Directed interleaved-branch sequences were added; all those previously surviving mutations are now rejected before its SoC screens run.

Neither variant is selected for physical implementation: both lose execution efficiency on both tested seeds and show no demonstrated resource or frequency advantage. This is a screening decision, not a claim that either violates a long-run baseline floor. The governing acceptance floors remain CoreMark >= 501.0657302224314 and CoreMark/LUT >= 0.053452712846429634; execution efficiency has not been converted into an additional hard nondecrease rule.

## Reproduction and next decision

Run profile_control.py in WSL only when build/control-events-current does not exist; it refuses to overwrite a completed run. Re-audit existing data with analyze_control.py. Eight test_control.py methods cover cycle conservation, missing/duplicate samples, fire/valid and WB relations, firmware opcode mismatch, truncated records, explicit stall priority and observation anchors.

Artifacts: build/control-events-current/invocation.json, analysis.json and uart.log.control.bin. Predictor screens: ../full_btb_correlated/build/v0 and v1; ../full_btb_correlated_recent/build/v0 and v1.

The current qualified version remains 151.2 MHz, 3.337708280819477 CoreMark/MHz, 0.053859284104579 CoreMark/LUT and 504.6614920599049 modeled CoreMark using 9370 full-system LUT. No measured hardware baseline changes. The profile supports focusing subsequent work on redirect recovery and the specific state-machine branch behavior, rather than treating every retirement gap as a data-cache wait or re-running these two correlation variants unchanged. Any replacement still needs full functional, paired long-run and complete-ILA timing/resource qualification. Board/electrical acceptance, the five non-AI tasks and continued optimization remain in scope; no browser access or GitHub upload occurs.
