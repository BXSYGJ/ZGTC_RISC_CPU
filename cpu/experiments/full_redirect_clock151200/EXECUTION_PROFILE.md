# Timed retirement profile of redirect priming

Measured September 10, 2026; paired analysis completed at the September 11 follow-up. This is an observation of the unchanged full_redirect_clock151200 CPU (81671AD0), not a new scoring image.

## Evidence and reproduction

Run profile_execution.py through WSL Python, then analyze_execution.py and compare_execution.py. The runner refuses to overwrite build/execution-profile-current. It reuses the byte-locked retirement observer, verifies the ELF against loaded firmware, derives timer-read PCs from disassembly, and checks the complete UART and parsed CoreMark result against short run 20260910-233631-e15b5716. Only the simulation observer changes; physical RTL is unchanged.

The paired comparison uses the unchanged full_control_commit profile and revalidates reports, executable and trace hashes, original short runs, current RTL, and observer inputs. It reconstructs the exact redirect-prime CPU substitutions. Both streams contain the same 2,748,929 retired PCs and instructions, including the two timer boundaries. Absolute simulation cycle origins differ and are not compared as elapsed time.

## Actual interval comparison

| Quantity | full_control_commit | Redirect priming |
| --- | ---: | ---: |
| Timed cycles | 3,060,873 | 3,004,340 |
| Extra cycles above one per adjacent retirement | 311,945 | 255,412 |
| Extra cycles following conditional branches | 276,369 | 222,661 |
| Extra cycles following JALR | 10,076 | 8,457 |
| Extra cycles following JAL | 6,960 | 5,754 |
| Extra cycles following other instructions | 18,540 | 18,540 |

Exactly 56,533 intervals improve by one cycle each, 2,692,395 intervals are unchanged, and none worsens in this trace. The saved cycles group as 53,708 after conditional branches, 1,619 after JALR and 1,206 after JAL. These totals conserve the measured 56,533-cycle reduction. They are retirement-interval groupings, not direct misprediction or mutually exclusive internal stall counters.

The largest remaining transition is 0x514 -> 0x518: 2,040 occurrences, with extra cycles reduced from 10,200 to 8,160. Conditional-branch-following intervals still account for 222,661 of 255,412 extra cycles. This supports further control-flow investigation, not a claim that all remaining extra cycles are removable.

## Decision boundary

The performance observation does not qualify the physical implementation. Ordinary 151.2 MHz seed 2 fails at -0.026 ns with 9,072 LUT. The completed full-ILA seed-2 retry fails at -0.159 ns with 9,399 LUT and 4,998 FF. Both retain their actual reports; the first full-ILA attempt stopped on memory allocation and is not a timing result. A serialized full-ILA seed-1 placement is a separate implementation attempt, not a relabeling of the failed seed-2 report.

The older rotation, fourth-history-bit folding and counter-policy screens already rejected their tested alternatives; this profile alone is not a reason to rerun them unchanged. No long-duration or board score is inferred from this short profile. The qualified parent and hardware baseline remain unchanged.
