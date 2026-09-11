# Full-system return-history metadata candidate

## Status

`full_return_history1` integrates the tested return-history representation with the unchanged `full_id_relation_mask1` CPU. GPIO, UART and the complete 42-data / 33-trigger / 1024-sample ILA remain required. No baseline is replaced and no long score or resource-efficiency qualification is claimed.

Ordinary PDS `20260911-071234-398f5b87` is terminal at 151.2 MHz: **9228 LUT / 4320 FF / WNS +0.076 ns**. Complete ILA `build/ila/return-history1-seed1` is terminal at **9633 LUT / 5058 FF / WNS -0.004 ns**, with three failing endpoints and TNS -0.012 ns. The candidate is rejected; no timing tolerance is relaxed. Native mapping retains all 42/33/1024 ILA dimensions and the full-system LUT count increases by one versus the parent. Bitstream SHA256 `3B8DD00AAAF60055A22890B2B8663EF832367C3CD659EE6E50FF6363CBEF7DBC`.

The two worst failing paths run from EX operand B bit 17 through compare/control to EX operand B bits 18/20 CE (ten levels, 2.146 ns logic and 4.054 ns routing). The third runs from EX instruction bit 15 to MEM result bit 26. Pinned independent ISA execution passes 196 runs, eight rejection controls and four auditor methods; invocation SHA256 `C2D32FF285C2E2491BDF277868DB317CF1EC427DDF49D7A7A86E01A1FB2CD976`.

## Source binding

CPU SHA256 `D37866F5E7EBB3D64D581C4C73B663EC742038C597B29953ABF1BF2AA53BE86B` is unchanged from the parent. BTB SHA256 `6E1B86520A18A36CBC8F5AE4ADA3568207660851EE794C8178879F5C44FB2030` includes exactly the four substitutions tested in `../return_history_metadata`. `change-receipt.json` records an empty immediate CPU delta, the four predictor substitutions and complete qualified-baseline ancestry. All nineteen other physical source inputs match the immediate parent.

Unconditional entries use otherwise-unused history bit zero for return classification. Conditional histories retain all bits, and the unchanged type-change allocation rule reinitializes history when an entry changes class. Every unconditional training event refreshes its return flag. The one-entry return stack, counters, tags, targets, reset/invalidation, exception behavior and pipeline interfaces are retained.

## Functional evidence

- Twenty-four source-bound safety methods pass, including the five 12000-cycle predictor differential configurations and five metadata fault rejections, inherited decode/redirect checks, masked relation tests, multiplier fallback/stall checks, stack and commit tests. Safety manifest SHA256 `4B8B360A9533822B959DA8775F06C8AF7EFE3776A2F3A31E6E7182E2D60E5FAA`.
- Six safety-auditor tests pass. Eight core/cache trace and final-memory comparisons pass against the independent reference; regression manifest SHA256 `477D55CC47A8642CB851976B0316A431FA815B8B67E540F3B04FED0BD11D8DA8`.
- All eight retirement traces, eight final memory dumps and both short UART logs are byte-identical to the immediate parent, recorded in `build/parent-behavior-comparison.json`. V0 remains 3000565 cycles / 2748941 retired / fcaf; V1 remains 3001255 / 2749614 / c64e. Short results are not long-run scores.

## Native synthesis evidence

`build/predictor-storage-comparison.json` binds both physical snapshots and actual synthesized netlists. The only source difference is the predictor. The two old `return_entry_0/1` GTP_RAM128X1DP cells, both with update_return data inputs, are absent. Predictor GTP_RAM128X1DP count falls from 20 to 18; the other observed predictor memory and parameterized flip-flop counts remain unchanged. Total ordinary synthesis LUT count falls from 8753 to 8728 (25 fewer). This is not the complete post-route LUT denominator and does not establish resource efficiency.

## Remaining gates

This candidate does not proceed to long runs or board tests because complete-system timing fails and post-route area does not improve. The parent long runs have completed, but their results cannot be relabeled as this changed predictor. Removing two inferred storage cells and 25 synthesis LUTs did not reduce routed area: ordinary LUTs increase by 17 and complete-system LUTs by one. Future optimization must target measured complete-system area and timing, not synthesis counts alone. No remote-board access or GitHub upload occurs.
