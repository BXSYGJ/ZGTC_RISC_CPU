# Two-way local-history BTB screen

## Completed physical result

The ordinary run 20260911-020416-a810df1b completes with 9231 LUT / 4437 FF and WNS -0.705 ns at 151.2 MHz. The complete ILA run build/ila/two-way-seed1-native-alias completes with 9669 full-system LUT / 5127 FF and WNS -0.531 ns. Its physical-qualification.json records physical_timing_passed=false, full_score_qualified=false and hardware_validated=false. This candidate is not promoted and has no reportable long-run score.

The failed first ILA attempt is retained: the Inserter cannot use core/pipeline_valid[3] for this particular ADF. Native net discovery identifies soc/unused_pipeline_valid[3]; audit_full_ila.py proves the exact CPU output-port wiring and register Q driver before accepting that alias. Actual native output confirms 42 data / 33 trigger channels and depth 1024. Eleven source, firmware, alias and actual-channel checks pass in build/full-ila-tests-complete.log. The initial incomplete map is a negative test fixture, not rewritten into a passing result.

The measured ordinary critical path passes through fetch_hit_second (105 loads) before reading the direction counters. The isolated sibling full_btb_two_way_parallel addresses this serialized lookup, preserving the exact short execution results while awaiting its own physical evidence. Historical launch notes below are retained for traceability; this completed result supersedes them.

## Design and motivation

This experiment retains 256 total BTB entries and the existing per-entry local history and counter banks, but groups entries into 128 two-way sets. A matching entry is updated in place, an invalid way is preferred, and a one-bit per-set replacement state tracks the least recently updated way. The tag includes the original folded-index high bit so merging two original index classes does not create false hits. It adds one tag bit per entry and one replacement bit per set; no LUT claim is made from declared bit counts. All non-predictor SoC RTL and firmware are unchanged.

Source-bound cold replay of 583674 committed control instructions across 370 unique PCs gives 8728 direct-mapped allocations versus 5520 with two ways. This replay is only a hypothesis screen: it is not the actual speculative fetch stream, does not reconstruct warm predictor state, and does not predict cycle savings. replay_conflicts.py records the trace and source hashes; test_replay.py has three passing cases.

## Actual matched execution screen

| Seed | Qualified parent cycles | Two-way cycles | Saved | Execution-efficiency ratio |
| --- | ---: | ---: | ---: | ---: |
| V0 | 3004340 | 3001251 | 3089 | 1.0010292374746397 |
| V1 | 3007840 | 2999526 | 8314 | 1.0027717712731945 |

Both complete ten-iteration results pass CRC and preserve retired counts (2748941 / 2749614). Independent predictor testing covers 72 parameter configurations, 24 rejected compiled mutations and two observationally equivalent unconditional-history cases, including directed same-set eviction/replacement sequences. These are short execution screens, not reportable scores or full-system timing/resource qualifications.

The initial build/v0 compilation is rejected by the warning gate: an eight-bit index was used for the 128-bit replacement state. The source now uses a correctly sized set index, including the two-entry parameter edge case; the warning is not suppressed. The failed build is retained. Passing runs are build/v0-widthfix and build/v1-widthfix. screen.py uses a validated --attempt label and refuses to overwrite any existing run.

## Physical follow-up

prepare_physical.py creates an immutable generated staging project with all twenty physical inputs, changing only the BTB. The first staging omitted the PDS Tcl template and stopped before launching native PDS; build/physical-project and its failed run 20260911-020215-75849ef6 are retained. The corrected staging at build/physical-project-complete includes hashed run_pds.ps1, build_pds.tcl, pds_soc_top.v.in and pds_report.py, and requires explicit firmware.

The actual ordinary PDS run is build/physical-project-complete/build/pds/20260911-020416-a810df1b, initially launched as PID 71332. It uses 151200000 Hz, M enabled, I-cache set bits 9, D-cache set bits 6, BTB index bits 8, all existing overlap/fast paths, RemoteLab UART 115200 and placement seed 1, with the existing 6000-iteration V0 firmware. Its process and reports must be checked live; launch is not completion.

The complete 42-data / 33-trigger / 1024-depth ILA implementation is still required after this source implementation, followed by paired long runs and source-bound metric checks if timing and total resources are favorable. Ordinary PDS numbers must not be used as the full-system LUT denominator. No current qualified version or hardware baseline is replaced. No browser or GitHub operation is performed.
